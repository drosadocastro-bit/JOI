import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable

from memory.summarizer_provider import ProviderGeneration, SummarizerProviderError


OPENAI_API_BASE_URL = 'https://api.openai.com/v1'
LUNA_INPUT_USD_PER_MILLION = 0.20
LUNA_CACHED_INPUT_USD_PER_MILLION = 0.02
LUNA_OUTPUT_USD_PER_MILLION = 1.20


class OpenAICompactSummarizerProvider:
    provider_id = 'openai'

    def __init__(
        self,
        api_key: str,
        model: str,
        cloud_authorized: Callable[[], bool],
        base_url: str = OPENAI_API_BASE_URL,
        timeout_seconds: int = 60,
        opener=urllib.request.urlopen,
    ):
        self._api_key = api_key
        self.model_id = model
        self._cloud_authorized = cloud_authorized
        self._base_url = self._validated_base_url(base_url)
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    @staticmethod
    def _validated_base_url(value: str) -> str:
        value = value.rstrip('/')
        parsed = urllib.parse.urlsplit(value)
        if not (
            parsed.scheme == 'https'
            and parsed.hostname == 'api.openai.com'
            and parsed.port in {None, 443}
            and parsed.path == '/v1'
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        ):
            raise ValueError('OpenAI base URL must be the official HTTPS endpoint')
        return value

    def health(self) -> dict:
        if not self._cloud_authorized():
            return {'ok': False, 'error': 'CLOUD is OFF'}
        api_key = self._api_key
        if not api_key:
            return {'ok': False, 'error': 'OPENAI_API_KEY is not configured'}
        request = self._request(
            f'/models/{urllib.parse.quote(self.model_id, safe="")}',
            api_key=api_key,
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            raise self._safe_error('OpenAI health check failed', exc, api_key) from exc
        return {
            'ok': payload.get('id') == self.model_id,
            'provider': self.provider_id,
            'model': self.model_id,
            'structured_outputs': True,
        }

    def generate(self, messages: list[dict], schema: dict) -> ProviderGeneration:
        if not self._cloud_authorized():
            raise SummarizerProviderError('CLOUD is OFF')
        api_key = self._api_key
        if not api_key:
            raise SummarizerProviderError('OPENAI_API_KEY is not configured')
        body = json.dumps({
            'model': self.model_id,
            'input': messages,
            'reasoning': {'effort': 'none'},
            'text': {
                'format': {
                    'type': 'json_schema',
                    'name': 'compact_memory_candidate',
                    'strict': True,
                    'schema': schema,
                },
            },
        }).encode('utf-8')
        request = self._request('/responses', body, api_key)
        started = time.perf_counter()
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            raise self._safe_error('OpenAI generation failed', exc, api_key) from exc
        latency = time.perf_counter() - started
        content = self._output_text(payload)
        usage = payload.get('usage') or {}
        input_tokens = usage.get('input_tokens')
        output_tokens = usage.get('output_tokens')
        cached_tokens = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
        cost = self._estimated_cost(input_tokens, output_tokens, cached_tokens)
        return ProviderGeneration(
            content=content,
            provider=self.provider_id,
            model=self.model_id,
            total_latency_seconds=latency,
            time_to_first_token_seconds=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )

    def reload_api_key(self, api_key: str) -> None:
        self._api_key = api_key

    def _request(self, path: str, body: bytes | None = None, api_key: str | None = None):
        headers = {'Authorization': f'Bearer {self._api_key if api_key is None else api_key}'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        return urllib.request.Request(
            f'{self._base_url}{path}',
            data=body,
            headers=headers,
            method='POST' if body is not None else 'GET',
        )

    def _safe_error(
        self,
        message: str,
        error: Exception,
        api_key: str | None = None,
    ) -> SummarizerProviderError:
        credential = self._api_key if api_key is None else api_key
        detail = str(error).replace(credential, '[REDACTED]') if credential else str(error)
        return SummarizerProviderError(f'{message}: {detail}')

    @staticmethod
    def _output_text(payload: dict) -> str:
        if payload.get('status') != 'completed':
            raise SummarizerProviderError('OpenAI response was incomplete')
        for output in payload.get('output', []):
            if output.get('type') != 'message':
                continue
            for content in output.get('content', []):
                if content.get('type') == 'refusal':
                    raise SummarizerProviderError('OpenAI refused the request')
                if content.get('type') == 'output_text':
                    return content.get('text', '')
        raise SummarizerProviderError('OpenAI response contained no output text')

    @staticmethod
    def _estimated_cost(input_tokens, output_tokens, cached_tokens):
        if input_tokens is None or output_tokens is None:
            return None
        uncached_tokens = max(0, input_tokens - cached_tokens)
        return (
            uncached_tokens * LUNA_INPUT_USD_PER_MILLION
            + cached_tokens * LUNA_CACHED_INPUT_USD_PER_MILLION
            + output_tokens * LUNA_OUTPUT_USD_PER_MILLION
        ) / 1_000_000
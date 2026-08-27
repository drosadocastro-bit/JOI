import json
import urllib.request
import urllib.error


class LocalLMStudioBrain:
    def __init__(self, base_url: str, model: str, timeout: int = 300):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout

    def health(self):
        url = f'{self.base_url}/models'
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
            model_ids = [item.get('id') for item in payload.get('data', [])]
            return {
                'ok': True,
                'endpoint': self.base_url,
                'models': model_ids,
                'selected_model': self.model,
                'selected_model_visible': self.model in model_ids,
            }
        except Exception as exc:
            return {
                'ok': False,
                'endpoint': self.base_url,
                'error': str(exc),
                'selected_model': self.model,
            }

    def chat(self, messages):
        url = f'{self.base_url}/chat/completions'
        payload = {'model': self.model, 'messages': messages, 'stream': False}
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            try:
                content = data['choices'][0]['message']['content']
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError('LM Studio returned an invalid response') from exc
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError('LM Studio returned an invalid response')
            return content
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode('utf-8', errors='ignore')
            raise RuntimeError(f'LM Studio HTTP {exc.code}: {detail}') from exc
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f'LM Studio request failed: {exc}') from exc

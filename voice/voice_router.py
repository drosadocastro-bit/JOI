import io
import json
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

from audio.playback import play_wav
from security.credential_provider import CredentialAccessError, CredentialProvider


ELEVENLABS_HOSTS = {
	'api.elevenlabs.io',
	'api.us.elevenlabs.io',
	'api.eu.residency.elevenlabs.io',
	'api.in.residency.elevenlabs.io',
	'api.sg.residency.elevenlabs.io',
}


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		return None


class VoiceRouter:
	def __init__(self, mode, local_provider=None, online_provider=None, logger=None):
		if mode not in {'local', 'online', 'hybrid'}:
			raise ValueError('voice mode must be local, online, or hybrid')
		if mode in {'local', 'hybrid'} and local_provider is None:
			raise ValueError(f'{mode} voice mode requires a local provider')
		if mode in {'online', 'hybrid'} and online_provider is None:
			raise ValueError(f'{mode} voice mode requires an online provider')

		self.mode = mode
		self.local_provider = local_provider
		self.online_provider = online_provider
		self.logger = logger
		self.active_provider = 'local' if mode == 'local' else 'online'

	def speak(self, text):
		if self.mode == 'local':
			self.active_provider = 'local'
			return self.local_provider.speak(text)
		if self.mode == 'online':
			self.active_provider = 'online'
			return self.online_provider.speak(text)

		try:
			self.active_provider = 'online'
			return self.online_provider.speak(text)
		except Exception as exc:
			if self.logger is not None:
				self.logger.warning('Online voice failed; falling back to local: %s', exc)
			self.active_provider = 'local'
			return self.local_provider.speak(text)


class KokoroVoiceRouter:
	def __init__(
		self,
		python_executable,
		model_path,
		voices_path,
		voice,
		language,
		output_path,
		timeout_seconds,
		playback_device_index=None,
	):
		self.python_executable = str(python_executable)
		self.model_path = str(model_path)
		self.voices_path = str(voices_path)
		self.voice = voice
		self.language = language
		self.output_path = Path(output_path)
		self.timeout_seconds = timeout_seconds
		self.playback_device_index = playback_device_index
		self.worker_path = Path(__file__).with_name('kokoro_worker.py')

	def speak(self, text):
		if not text or not text.strip():
			raise ValueError('text must not be empty')

		self.output_path.parent.mkdir(parents=True, exist_ok=True)
		self.output_path.unlink(missing_ok=True)
		command = [
			self.python_executable,
			str(self.worker_path),
			'--model', self.model_path,
			'--voices', self.voices_path,
			'--voice', self.voice,
			'--language', self.language,
			'--output', str(self.output_path),
		]
		result = subprocess.run(
			command,
			input=text,
			capture_output=True,
			text=True,
			encoding='utf-8',
			timeout=self.timeout_seconds,
			check=False,
		)
		if result.returncode != 0:
			detail = result.stderr.strip() or 'Kokoro worker failed without details'
			raise RuntimeError(detail)

		try:
			payload = json.loads(result.stdout)
			generated_path = Path(payload['output'])
		except (json.JSONDecodeError, KeyError, TypeError) as exc:
			raise RuntimeError('Kokoro worker returned an invalid response') from exc
		if generated_path.resolve() != self.output_path.resolve() or not generated_path.is_file():
			raise RuntimeError('Kokoro worker did not create the configured output file')

		play_wav(generated_path, device_index=self.playback_device_index)
		return generated_path


class ElevenLabsVoiceProvider:
	def __init__(
		self,
		credential_provider: CredentialProvider,
		voice_id,
		model_id,
		base_url,
		output_path,
		timeout_seconds,
		cloud_authorized,
		playback_device_index=None,
		opener=None,
	):
		if not voice_id:
			raise ValueError('ElevenLabs voice ID is required')

		self.base_url = self._validated_base_url(base_url)
		self._credential_provider = credential_provider
		self._cloud_authorized = cloud_authorized
		self.voice_id = voice_id
		self.model_id = model_id
		self.output_path = Path(output_path)
		self.timeout_seconds = timeout_seconds
		self.playback_device_index = playback_device_index
		self.opener = opener or urllib.request.build_opener(NoRedirectHandler()).open

	@staticmethod
	def _validated_base_url(value):
		value = value.rstrip('/')
		parsed = urllib.parse.urlsplit(value)
		trusted = (
			parsed.scheme == 'https'
			and parsed.hostname in ELEVENLABS_HOSTS
			and parsed.port in {None, 443}
			and parsed.path == '/v1'
			and not parsed.username
			and not parsed.password
			and not parsed.query
			and not parsed.fragment
		)
		if not trusted:
			raise ValueError('ElevenLabs base URL must be an official HTTPS endpoint')
		return value

	def speak(self, text):
		if not text or not text.strip():
			raise ValueError('text must not be empty')
		if not self._cloud_authorized():
			raise RuntimeError('CLOUD is OFF')
		try:
			api_key = self._credential_provider.get_elevenlabs_credential()
		except CredentialAccessError:
			raise RuntimeError('ElevenLabs credential is unavailable') from None

		voice_id = urllib.parse.quote(self.voice_id, safe='')
		url = f'{self.base_url}/text-to-speech/{voice_id}?output_format=wav_24000'
		payload = json.dumps({
			'text': text,
			'model_id': self.model_id,
		}).encode('utf-8')
		request = urllib.request.Request(
			url,
			data=payload,
			headers={
				'Accept': 'audio/wav',
				'Content-Type': 'application/json',
				'xi-api-key': api_key,
			},
			method='POST',
		)

		try:
			with self.opener(request, timeout=self.timeout_seconds) as response:
				content_type = response.headers.get('Content-Type', '').lower()
				audio_bytes = response.read()
		except Exception as exc:
			detail = str(exc).replace(api_key, '[REDACTED]')
			raise RuntimeError(f'ElevenLabs request failed: {detail}') from None

		if not (content_type.startswith('audio/') or content_type == 'application/octet-stream'):
			raise RuntimeError('ElevenLabs returned an invalid audio response')
		try:
			with wave.open(io.BytesIO(audio_bytes), 'rb') as audio:
				valid_audio = (
					audio.getnframes() > 0
					and audio.getframerate() == 24000
					and audio.getsampwidth() == 2
					and audio.getcomptype() == 'NONE'
				)
		except (EOFError, wave.Error) as exc:
			raise RuntimeError('ElevenLabs returned an invalid audio response') from exc
		if not valid_audio:
			raise RuntimeError('ElevenLabs returned an invalid audio response')

		self.output_path.parent.mkdir(parents=True, exist_ok=True)
		temporary_path = self.output_path.with_suffix(f'{self.output_path.suffix}.tmp')
		try:
			temporary_path.write_bytes(audio_bytes)
			temporary_path.replace(self.output_path)
		finally:
			temporary_path.unlink(missing_ok=True)

		play_wav(self.output_path, device_index=self.playback_device_index)
		return self.output_path

	def health(self):
		if not self._cloud_authorized():
			return {'ok': False, 'error': 'CLOUD is OFF'}
		try:
			api_key = self._credential_provider.get_elevenlabs_credential()
		except CredentialAccessError:
			return {'ok': False, 'error': 'ElevenLabs credential is unavailable'}
		request = urllib.request.Request(
			f'{self.base_url}/user',
			headers={'Accept': 'application/json', 'xi-api-key': api_key},
			method='GET',
		)
		try:
			with self.opener(request, timeout=self.timeout_seconds) as response:
				payload = json.loads(response.read().decode('utf-8'))
		except Exception as exc:
			detail = str(exc).replace(api_key, '[REDACTED]')
			raise RuntimeError(f'ElevenLabs health check failed: {detail}') from None
		return {'ok': isinstance(payload, dict), 'provider': 'elevenlabs'}

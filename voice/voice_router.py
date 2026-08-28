import json
import subprocess
from pathlib import Path

from audio.playback import play_wav


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

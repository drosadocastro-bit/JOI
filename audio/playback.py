import wave
from pathlib import Path

import sounddevice


def play_wav(path, device_index):
	input_path = Path(path)
	with wave.open(str(input_path), 'rb') as audio:
		channels = audio.getnchannels()
		samplerate = audio.getframerate()
		if audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
			raise ValueError('Playback requires uncompressed 16-bit PCM WAV audio')

		sounddevice.check_output_settings(
			device=device_index,
			channels=channels,
			dtype='int16',
			samplerate=samplerate,
		)
		with sounddevice.RawOutputStream(
			device=device_index,
			channels=channels,
			dtype='int16',
			samplerate=samplerate,
		) as stream:
			while data := audio.readframes(1024):
				stream.write(data)

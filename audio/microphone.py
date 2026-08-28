import wave
from pathlib import Path

import sounddevice


def record_wav(path, duration_seconds, device_index, samplerate=16000, channels=1):
	if duration_seconds <= 0:
		raise ValueError('duration_seconds must be positive')
	if samplerate <= 0:
		raise ValueError('samplerate must be positive')
	if channels <= 0:
		raise ValueError('channels must be positive')

	sounddevice.check_input_settings(
		device=device_index,
		channels=channels,
		dtype='int16',
		samplerate=samplerate,
	)
	output_path = Path(path)
	output_path.parent.mkdir(parents=True, exist_ok=True)
	frames_remaining = round(duration_seconds * samplerate)

	with wave.open(str(output_path), 'wb') as output:
		output.setnchannels(channels)
		output.setsampwidth(2)
		output.setframerate(samplerate)
		with sounddevice.RawInputStream(
			device=device_index,
			channels=channels,
			dtype='int16',
			samplerate=samplerate,
		) as stream:
			while frames_remaining:
				frame_count = min(frames_remaining, 1024)
				data, overflowed = stream.read(frame_count)
				if overflowed:
					raise RuntimeError('Microphone input overflowed')
				output.writeframesraw(bytes(data))
				frames_remaining -= frame_count

	return output_path

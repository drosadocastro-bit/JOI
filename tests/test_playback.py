import wave
from unittest.mock import MagicMock, patch

import pytest

from audio.playback import play_wav


def _write_wav(path, sample_width=2):
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(sample_width)
        audio.setframerate(16000)
        audio.writeframes(b'\x01' * sample_width * 8)


@patch('audio.playback.sounddevice.RawOutputStream')
@patch('audio.playback.sounddevice.check_output_settings')
def test_play_wav_writes_pcm_to_selected_device(check_settings, output_stream, tmp_path):
    path = tmp_path / 'reply.wav'
    _write_wav(path)
    stream = MagicMock()
    output_stream.return_value.__enter__.return_value = stream

    play_wav(path, device_index=5)

    check_settings.assert_called_once_with(
        device=5,
        channels=1,
        dtype='int16',
        samplerate=16000,
    )
    stream.write.assert_called_once_with(b'\x01\x01' * 8)


def test_play_wav_rejects_unsupported_sample_width(tmp_path):
    path = tmp_path / 'reply.wav'
    _write_wav(path, sample_width=1)

    with pytest.raises(ValueError, match='16-bit PCM'):
        play_wav(path, device_index=5)
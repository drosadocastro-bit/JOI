import wave
from unittest.mock import MagicMock, patch

import pytest

from audio.microphone import record_wav


@patch('audio.microphone.sounddevice.RawInputStream')
@patch('audio.microphone.sounddevice.check_input_settings')
def test_record_wav_writes_pcm_audio(_check_settings, input_stream, tmp_path):
    stream = MagicMock()
    stream.read.return_value = (b'\x01\x00' * 8, False)
    input_stream.return_value.__enter__.return_value = stream
    path = tmp_path / 'capture.wav'

    assert record_wav(path, duration_seconds=1, device_index=3, samplerate=8) == path

    _check_settings.assert_called_once_with(
        device=3,
        channels=1,
        dtype='int16',
        samplerate=8,
    )
    with wave.open(str(path), 'rb') as recording:
        assert recording.getnchannels() == 1
        assert recording.getsampwidth() == 2
        assert recording.getframerate() == 8
        assert recording.getnframes() == 8


def test_record_wav_rejects_non_positive_duration(tmp_path):
    with pytest.raises(ValueError, match='duration_seconds must be positive'):
        record_wav(tmp_path / 'capture.wav', 0, device_index=3)


@patch('audio.microphone.sounddevice.RawInputStream')
@patch('audio.microphone.sounddevice.check_input_settings')
def test_record_wav_fails_on_input_overflow(_check_settings, input_stream, tmp_path):
    stream = MagicMock()
    stream.read.return_value = (b'\x00\x00' * 8, True)
    input_stream.return_value.__enter__.return_value = stream

    with pytest.raises(RuntimeError, match='input overflowed'):
        record_wav(tmp_path / 'capture.wav', 1, device_index=3, samplerate=8)
from unittest.mock import patch

import pytest

from audio.devices import AudioDevice, find_device, list_devices


DEVICES = [
    {'name': 'Microphone Array (Realtek)', 'max_input_channels': 2, 'max_output_channels': 0, 'default_samplerate': 48000.0},
    {'name': 'Speakers (Realtek)', 'max_input_channels': 0, 'max_output_channels': 2, 'default_samplerate': 48000.0},
    {'name': 'Disabled', 'max_input_channels': 0, 'max_output_channels': 0, 'default_samplerate': 0.0},
]


@patch('audio.devices.sounddevice.query_devices', return_value=DEVICES)
def test_list_devices_omits_devices_without_channels(_query_devices):
    assert list_devices() == [
        AudioDevice(0, 'Microphone Array (Realtek)', 2, 0, 48000),
        AudioDevice(1, 'Speakers (Realtek)', 0, 2, 48000),
    ]


@patch('audio.devices.sounddevice.query_devices', return_value=DEVICES)
def test_find_device_matches_name_and_capability(_query_devices):
    assert find_device('microphone array', 'input').index == 0
    assert find_device('speakers', 'output').index == 1


@patch('audio.devices.sounddevice.query_devices', return_value=DEVICES)
def test_find_device_rejects_wrong_capability(_query_devices):
    with pytest.raises(LookupError, match='No output audio device'):
        find_device('microphone', 'output')
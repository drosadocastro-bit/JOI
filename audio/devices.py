from dataclasses import dataclass

import sounddevice


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    input_channels: int
    output_channels: int
    default_samplerate: int


def list_devices():
    devices = []
    for index, details in enumerate(sounddevice.query_devices()):
        input_channels = int(details['max_input_channels'])
        output_channels = int(details['max_output_channels'])
        if not input_channels and not output_channels:
            continue
        devices.append(AudioDevice(
            index=index,
            name=str(details['name']),
            input_channels=input_channels,
            output_channels=output_channels,
            default_samplerate=int(details['default_samplerate']),
        ))
    return devices


def find_device(name, capability):
    if capability not in {'input', 'output'}:
        raise ValueError("capability must be 'input' or 'output'")
    matches = [
        device for device in list_devices()
        if name.casefold() in device.name.casefold()
        and getattr(device, f'{capability}_channels') > 0
    ]
    if not matches:
        raise LookupError(f'No {capability} audio device matches {name!r}')
    if len(matches) > 1:
        names = ', '.join(f'{device.index}: {device.name}' for device in matches)
        raise LookupError(f'Multiple {capability} audio devices match {name!r}: {names}')
    return matches[0]
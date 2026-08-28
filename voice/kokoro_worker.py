import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--voices', type=Path, required=True)
    parser.add_argument('--voice', required=True)
    parser.add_argument('--language', required=True)
    parser.add_argument('--output', type=Path, required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    text = sys.stdin.read()
    if not text.strip():
        raise ValueError('text must not be empty')
    if not args.model.is_file() or not args.voices.is_file():
        raise FileNotFoundError('Kokoro model or voices file is missing')

    model = Kokoro(str(args.model), str(args.voices))
    waveform, sample_rate = model.create(
        text,
        voice=args.voice,
        lang=args.language,
    )
    waveform = np.asarray(waveform, dtype=np.float32)
    if sample_rate <= 0 or waveform.size == 0 or not np.isfinite(waveform).all():
        raise RuntimeError('Kokoro generated invalid audio')

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, waveform, sample_rate, subtype='PCM_16')
    print(json.dumps({'output': str(args.output.resolve()), 'sample_rate': sample_rate}))


if __name__ == '__main__':
    main()
"""Benchmark one Qwen3-TTS generation in the isolated TTS environment."""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel


DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
DEFAULT_TEXT = "Hello. This is JOI testing local speech synthesis on the CPU."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--speaker", default="Ryan")
    parser.add_argument("--language", default="English")
    parser.add_argument("--output", type=Path, default=Path("data/tts-benchmark.wav"))
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow Hugging Face model downloads. Without this flag, cache only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    stop_sampling = threading.Event()

    def sample_memory() -> None:
        nonlocal peak_rss
        while not stop_sampling.wait(0.1):
            peak_rss = max(peak_rss, process.memory_info().rss)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    started = time.perf_counter()

    try:
        model = Qwen3TTSModel.from_pretrained(
            args.model,
            device_map="cpu",
            dtype=torch.float32,
            local_files_only=not args.allow_download,
        )
        loaded = time.perf_counter()
        waveforms, sample_rate = model.generate_custom_voice(
            text=args.text,
            speaker=args.speaker,
            language=args.language,
            non_streaming_mode=True,
        )
        generated = time.perf_counter()

        waveform = np.asarray(waveforms[0], dtype=np.float32)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(args.output, waveform, sample_rate, subtype="PCM_16")

        metrics = {
            "model": args.model,
            "device": "cpu",
            "torch_version": torch.__version__,
            "load_seconds": round(loaded - started, 3),
            "generation_seconds": round(generated - loaded, 3),
            "audio_seconds": round(len(waveform) / sample_rate, 3),
            "real_time_factor": round((generated - loaded) / (len(waveform) / sample_rate), 3),
            "peak_rss_gib": round(peak_rss / (1024**3), 3),
            "sample_rate": sample_rate,
            "output": str(args.output.resolve()),
        }
        print(json.dumps(metrics, indent=2))
    finally:
        stop_sampling.set()
        sampler.join()


if __name__ == "__main__":
    main()
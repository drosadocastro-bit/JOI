"""Benchmark Kokoro ONNX for JOI's offline interactive TTS requirements."""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf
from kokoro_onnx import Kokoro


DEFAULT_MODEL = Path(r"D:\JOI\models\kokoro\kokoro-v1.0.onnx")
DEFAULT_VOICES = Path(r"D:\JOI\models\kokoro\voices-v1.0.bin")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--voices", type=Path, default=DEFAULT_VOICES)
    parser.add_argument("--output-dir", type=Path, default=Path("data/kokoro-benchmark"))
    parser.add_argument("--soak-count", type=int, default=20)
    return parser.parse_args()


def validate_waveform(waveform: np.ndarray, sample_rate: int) -> None:
    if sample_rate <= 0 or waveform.size == 0:
        raise ValueError("generated audio is empty or has an invalid sample rate")
    if not np.isfinite(waveform).all() or float(np.max(np.abs(waveform))) == 0:
        raise ValueError("generated audio is silent or contains non-finite samples")


def generate_case(
    model: Kokoro,
    output_dir: Path,
    *,
    name: str,
    text: str,
    voice: str,
    language: str,
) -> dict[str, object]:
    started = time.perf_counter()
    waveform, sample_rate = model.create(text, voice=voice, lang=language)
    generation_seconds = time.perf_counter() - started
    waveform = np.asarray(waveform, dtype=np.float32)
    validate_waveform(waveform, sample_rate)

    output = output_dir / f"{name}.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output, waveform, sample_rate, subtype="PCM_16")
    audio_seconds = len(waveform) / sample_rate
    return {
        "name": name,
        "generation_seconds": round(generation_seconds, 3),
        "audio_seconds": round(audio_seconds, 3),
        "real_time_factor": round(generation_seconds / audio_seconds, 3),
        "sample_rate": sample_rate,
        "output": str(output.resolve()),
    }


async def measure_streaming(model: Kokoro, output_dir: Path) -> dict[str, object]:
    started = time.perf_counter()
    chunks: list[np.ndarray] = []
    sample_rate = 0
    first_audio_seconds: float | None = None

    async for chunk, chunk_sample_rate in model.create_stream(
        "JOI is testing true local streaming. The first audio chunk should arrive quickly.",
        voice="af_heart",
        lang="en-us",
    ):
        if first_audio_seconds is None:
            first_audio_seconds = time.perf_counter() - started
        waveform = np.asarray(chunk, dtype=np.float32)
        validate_waveform(waveform, chunk_sample_rate)
        chunks.append(waveform)
        sample_rate = chunk_sample_rate

    if first_audio_seconds is None:
        raise ValueError("stream produced no audio")
    combined = np.concatenate(chunks)
    output = output_dir / "streaming.wav"
    sf.write(output, combined, sample_rate, subtype="PCM_16")
    total_seconds = time.perf_counter() - started
    return {
        "first_audio_seconds": round(first_audio_seconds, 3),
        "generation_seconds": round(total_seconds, 3),
        "audio_seconds": round(len(combined) / sample_rate, 3),
        "chunks": len(chunks),
        "output": str(output.resolve()),
    }


def main() -> None:
    args = parse_args()
    if args.soak_count < 1:
        raise ValueError("soak-count must be positive")
    for path in (args.model, args.voices):
        if not path.is_file():
            raise FileNotFoundError(f"Required local artifact not found: {path}")

    process = psutil.Process()
    peak_rss = process.memory_info().rss
    stop_sampling = threading.Event()

    def sample_memory() -> None:
        nonlocal peak_rss
        while not stop_sampling.wait(0.05):
            peak_rss = max(peak_rss, process.memory_info().rss)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    try:
        load_started = time.perf_counter()
        model = Kokoro(str(args.model), str(args.voices))
        load_seconds = time.perf_counter() - load_started
        cases = [
            generate_case(
                model,
                args.output_dir,
                name="english_cold",
                text="Hello. JOI is speaking locally on this computer.",
                voice="af_heart",
                language="en-us",
            ),
            generate_case(
                model,
                args.output_dir,
                name="spanish",
                text="Hola. JOI está hablando localmente en esta computadora.",
                voice="ef_dora",
                language="es",
            ),
            generate_case(
                model,
                args.output_dir,
                name="punctuation",
                text="Wait... really? Yes! JOI says: ready, steady, go.",
                voice="af_heart",
                language="en-us",
            ),
            generate_case(
                model,
                args.output_dir,
                name="english_warm",
                text="Hello. JOI is speaking locally on this computer.",
                voice="af_heart",
                language="en-us",
            ),
            generate_case(
                model,
                args.output_dir,
                name="long_text",
                text=(
                    "JOI is running a local text to speech acceptance test. "
                    "Each sentence can be streamed as a bounded audio segment. "
                    "This keeps long replies responsive and preserves their original order."
                ),
                voice="af_heart",
                language="en-us",
            ),
        ]
        streaming = asyncio.run(measure_streaming(model, args.output_dir))
        soak = [
            generate_case(
                model,
                args.output_dir / "soak",
                name=f"soak_{index + 1:02d}",
                text=f"Local voice stability check {index + 1}.",
                voice="af_heart",
                language="en-us",
            )
            for index in range(args.soak_count)
        ]
        report = {
            "model": str(args.model.resolve()),
            "runtime": "kokoro-onnx==0.6.1",
            "device": "CPUExecutionProvider",
            "load_seconds": round(load_seconds, 3),
            "peak_rss_gib": round(peak_rss / (1024**3), 3),
            "cases": cases,
            "streaming": streaming,
            "soak": {
                "generations": len(soak),
                "mean_real_time_factor": round(
                    sum(float(result["real_time_factor"]) for result in soak) / len(soak),
                    3,
                ),
                "results": soak,
            },
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
    finally:
        stop_sampling.set()
        sampler.join()


if __name__ == "__main__":
    main()
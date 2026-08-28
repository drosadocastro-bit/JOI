"""Run auditable CPU acceptance checks for the selected Qwen3-TTS model."""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel


DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
LONG_TEXT = (
    "JOI is running a local text to speech acceptance test. "
    "Each sentence is synthesized separately so long replies can be played in bounded chunks. "
    "The chunks are joined with a short pause while preserving their original order."
)


@dataclass(frozen=True)
class GenerationResult:
    name: str
    status: str
    generation_seconds: float
    audio_seconds: float
    real_time_factor: float
    chunks: int
    output: str
    detail: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--speaker", default="Ryan")
    parser.add_argument("--output-dir", type=Path, default=Path("data/tts-acceptance"))
    parser.add_argument("--report", type=Path, default=Path("data/logs/tts-acceptance.json"))
    parser.add_argument("--soak-count", type=int, default=20)
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow Hugging Face downloads. Without this flag, cache only.",
    )
    return parser.parse_args()


def split_sentences(text: str) -> list[str]:
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()]
    return chunks or [text.strip()]


def validate_waveform(waveform: np.ndarray, sample_rate: int) -> None:
    if sample_rate <= 0:
        raise ValueError("sample rate must be positive")
    if waveform.size == 0:
        raise ValueError("generated waveform is empty")
    if not np.isfinite(waveform).all():
        raise ValueError("generated waveform contains non-finite samples")
    if float(np.max(np.abs(waveform))) == 0:
        raise ValueError("generated waveform is silent")


def generate_case(
    model: Qwen3TTSModel,
    *,
    name: str,
    text: str,
    language: str,
    speaker: str,
    output_dir: Path,
    chunked: bool = False,
) -> GenerationResult:
    texts = split_sentences(text) if chunked else [text]
    waveforms: list[np.ndarray] = []
    sample_rate: int | None = None
    started = time.perf_counter()

    for chunk in texts:
        generated, chunk_sample_rate = model.generate_custom_voice(
            text=chunk,
            speaker=speaker,
            language=language,
            non_streaming_mode=True,
        )
        waveform = np.asarray(generated[0], dtype=np.float32)
        validate_waveform(waveform, chunk_sample_rate)
        if sample_rate is not None and chunk_sample_rate != sample_rate:
            raise ValueError("sample rate changed between chunks")
        sample_rate = chunk_sample_rate
        waveforms.append(waveform)

    generation_seconds = time.perf_counter() - started
    assert sample_rate is not None
    pause = np.zeros(round(sample_rate * 0.12), dtype=np.float32)
    combined_parts: list[np.ndarray] = []
    for index, waveform in enumerate(waveforms):
        if index:
            combined_parts.append(pause)
        combined_parts.append(waveform)
    combined = np.concatenate(combined_parts)
    validate_waveform(combined, sample_rate)

    output = output_dir / f"{name}.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output, combined, sample_rate, subtype="PCM_16")
    audio_seconds = len(combined) / sample_rate
    return GenerationResult(
        name=name,
        status="passed",
        generation_seconds=round(generation_seconds, 3),
        audio_seconds=round(audio_seconds, 3),
        real_time_factor=round(generation_seconds / audio_seconds, 3),
        chunks=len(texts),
        output=str(output.resolve()),
    )


def main() -> None:
    args = parse_args()
    if args.soak_count < 1:
        raise ValueError("soak-count must be positive")

    process = psutil.Process()
    peak_rss = process.memory_info().rss
    stop_sampling = threading.Event()

    def sample_memory() -> None:
        nonlocal peak_rss
        while not stop_sampling.wait(0.1):
            peak_rss = max(peak_rss, process.memory_info().rss)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    suite_started = time.perf_counter()

    try:
        load_started = time.perf_counter()
        model = Qwen3TTSModel.from_pretrained(
            args.model,
            device_map="cpu",
            dtype=torch.float32,
            local_files_only=not args.allow_download,
        )
        load_seconds = time.perf_counter() - load_started

        cases = [
            ("english", "Hello. JOI is speaking locally on this computer.", "English", False),
            ("spanish", "Hola. JOI esta hablando localmente en esta computadora.", "Spanish", False),
            ("punctuation", "Wait... really? Yes! JOI says: ready, steady, go.", "English", False),
            ("long_text", LONG_TEXT, "English", True),
        ]
        results = [
            generate_case(
                model,
                name=name,
                text=text,
                language=language,
                speaker=args.speaker,
                output_dir=args.output_dir,
                chunked=chunked,
            )
            for name, text, language, chunked in cases
        ]

        soak_results = [
            generate_case(
                model,
                name=f"soak_{index + 1:02d}",
                text=f"Local voice stability check {index + 1}.",
                language="English",
                speaker=args.speaker,
                output_dir=args.output_dir / "soak",
            )
            for index in range(args.soak_count)
        ]
        results.extend(soak_results)

        report = {
            "model": args.model,
            "device": "cpu",
            "torch_version": torch.__version__,
            "status": "failed_interactive_gate",
            "load_seconds": round(load_seconds, 3),
            "suite_seconds": round(time.perf_counter() - suite_started, 3),
            "peak_rss_gib": round(peak_rss / (1024**3), 3),
            "soak": {"status": "passed", "generations": len(soak_results)},
            "unsupported": {
                "style_instructions": "The 0.6B CustomVoice implementation discards instruct.",
                "first_audio_latency": "The API does not expose true streaming generation.",
            },
            "results": [asdict(result) for result in results],
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        stop_sampling.set()
        sampler.join()


if __name__ == "__main__":
    main()
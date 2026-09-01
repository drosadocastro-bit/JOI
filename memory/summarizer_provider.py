from dataclasses import dataclass
from typing import Protocol


class SummarizerProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderGeneration:
    content: str
    provider: str
    model: str
    total_latency_seconds: float | None = None
    time_to_first_token_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None


class SummarizerProvider(Protocol):
    provider_id: str
    model_id: str

    def health(self) -> dict: ...

    def generate(self, messages: list[dict], schema: dict) -> ProviderGeneration: ...
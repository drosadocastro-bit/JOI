import json
import os
import queue
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from memory.memory_store import EffectiveMemorySnapshot, EpisodicTurn
from memory.summarizer_provider import SummarizerProviderError


COMPACT_MEMORY_SCHEMA_VERSION = 1


class CompactMemoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompactSource:
    turn_id: str
    role: str
    content: str

    def render(self) -> str:
        return f'[{self.turn_id}] {self.role.upper()}: {self.content}'


@dataclass(frozen=True)
class CompactMemoryDraft:
    sources: tuple[CompactSource, ...]


@dataclass(frozen=True)
class CompactMemoryState:
    summary: str
    sources: tuple[CompactSource, ...]
    source_turn_ids: tuple[str, ...]
    updated_at_utc: str
    summarizer_version: str
    schema_version: int = COMPACT_MEMORY_SCHEMA_VERSION


@dataclass(frozen=True)
class CompactClaim:
    claim_id: str
    text: str
    source_turn_ids: tuple[str, ...]
    source_policy_ids: tuple[str | None, ...]
    confidence: float
    status: str
    generated_at_utc: str
    summarizer: str


@dataclass(frozen=True)
class ModelCompactMemoryCandidate:
    summary_version: int
    generated_at_utc: str
    summarizer: str
    source_policy_revision: int
    claims: tuple[CompactClaim, ...]
    provider: str | None = None
    model: str | None = None


class CompactSummarizer(Protocol):
    version: str

    def __call__(
        self,
        previous: CompactMemoryState | None,
        turns: Sequence[EpisodicTurn],
    ) -> CompactMemoryDraft: ...


def _normalized_content(content: str) -> str:
    return ' '.join(content.split())


def _require_utc_timestamp(value: str) -> None:
    try:
        timestamp = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CompactMemoryError('model candidate is malformed') from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise CompactMemoryError('model candidate is malformed')


def parse_model_candidate(raw: str) -> ModelCompactMemoryCandidate:
    try:
        payload = json.loads(raw)
        legacy_fields = {
            'summary_version', 'generated_at_utc', 'summarizer',
            'source_policy_revision', 'claims',
        }
        candidate_fields = legacy_fields | {'provider', 'model'}
        if frozenset(payload) not in {frozenset(legacy_fields), frozenset(candidate_fields)}:
            raise CompactMemoryError('model candidate is malformed')
        provider = payload.get('provider')
        model = payload.get('model')
        if (provider is None) != (model is None):
            raise CompactMemoryError('model candidate provenance is malformed')
        if provider is not None and (
            not isinstance(provider, str) or not provider
            or not isinstance(model, str) or not model
        ):
            raise CompactMemoryError('model candidate provenance is malformed')
        if payload['summary_version'] != 1:
            raise CompactMemoryError('model candidate is malformed')
        if not isinstance(payload['summarizer'], str) or not payload['summarizer']:
            raise CompactMemoryError('model candidate is malformed')
        if (
            isinstance(payload['source_policy_revision'], bool)
            or not isinstance(payload['source_policy_revision'], int)
            or payload['source_policy_revision'] < 0
        ):
            raise CompactMemoryError('model candidate is malformed')
        if not isinstance(payload['claims'], list):
            raise CompactMemoryError('model candidate is malformed')
        _require_utc_timestamp(payload['generated_at_utc'])
        claims = tuple(_claim_from_payload(item) for item in payload['claims'])
        claim_ids = [claim.claim_id for claim in claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise CompactMemoryError('duplicate claim IDs')
        if any(
            claim.summarizer != payload['summarizer']
            or claim.generated_at_utc != payload['generated_at_utc']
            for claim in claims
        ):
            raise CompactMemoryError('model candidate metadata is inconsistent')
        return ModelCompactMemoryCandidate(
            summary_version=payload['summary_version'],
            generated_at_utc=payload['generated_at_utc'],
            summarizer=payload['summarizer'],
            source_policy_revision=payload['source_policy_revision'],
            claims=claims,
            provider=provider,
            model=model,
        )
    except CompactMemoryError:
        raise
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CompactMemoryError('model candidate is malformed') from exc


def _claim_from_payload(payload) -> CompactClaim:
    required = {
        'claim_id', 'text', 'source_turn_ids', 'source_policy_ids', 'confidence',
        'status', 'generated_at_utc', 'summarizer',
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise CompactMemoryError('model candidate is malformed')
    source_turn_ids = payload['source_turn_ids']
    source_policy_ids = payload['source_policy_ids']
    if (
        not isinstance(source_turn_ids, list)
        or not source_turn_ids
        or any(not isinstance(item, str) or not item for item in source_turn_ids)
        or len(set(source_turn_ids)) != len(source_turn_ids)
        or not isinstance(source_policy_ids, list)
        or len(source_policy_ids) != len(source_turn_ids)
        or any(item is not None and not isinstance(item, str) for item in source_policy_ids)
    ):
        raise CompactMemoryError('claim provenance is malformed')
    if payload['status'] != 'explicit':
        raise CompactMemoryError('inferred claims are not accepted')
    confidence = payload['confidence']
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise CompactMemoryError('model candidate is malformed')
    if not 0 <= confidence <= 1:
        raise CompactMemoryError('model candidate is malformed')
    if any(
        not isinstance(payload[field], str) or not payload[field]
        for field in ('claim_id', 'text', 'generated_at_utc', 'summarizer')
    ):
        raise CompactMemoryError('model candidate is malformed')
    _require_utc_timestamp(payload['generated_at_utc'])
    return CompactClaim(
        claim_id=payload['claim_id'],
        text=_normalized_content(payload['text']),
        source_turn_ids=tuple(source_turn_ids),
        source_policy_ids=tuple(source_policy_ids),
        confidence=float(confidence),
        status=payload['status'],
        generated_at_utc=payload['generated_at_utc'],
        summarizer=payload['summarizer'],
    )


class ModelCompactMemoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> ModelCompactMemoryCandidate | None:
        if not self.path.exists():
            return None
        try:
            return parse_model_candidate(self.path.read_text(encoding='utf-8'))
        except CompactMemoryError:
            raise
        except OSError as exc:
            raise CompactMemoryError('could not load model compact memory') from exc

    def save(self, candidate: ModelCompactMemoryCandidate) -> None:
        temporary_path = self.path.with_suffix(f'{self.path.suffix}.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = asdict(candidate)
            with temporary_path.open('w', encoding='utf-8', newline='\n') as stream:
                json.dump(payload, stream, ensure_ascii=True, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(self.path)
        except OSError as exc:
            raise CompactMemoryError('could not save model compact memory') from exc
        finally:
            temporary_path.unlink(missing_ok=True)


class ModelCompactMemoryManager:
    def __init__(
        self,
        store: ModelCompactMemoryStore,
        summarizer,
        policy_revision_reader: Callable[[], int] | None = None,
    ):
        self.store = store
        self.summarizer = summarizer
        self.policy_revision_reader = policy_revision_reader
        self.state = store.load()

    def update(
        self,
        snapshot: EffectiveMemorySnapshot,
    ) -> ModelCompactMemoryCandidate:
        try:
            candidate = self.summarizer(snapshot)
        except CompactMemoryError:
            raise
        except Exception as exc:
            raise CompactMemoryError('model summarizer failed') from exc
        if not isinstance(candidate, ModelCompactMemoryCandidate):
            raise CompactMemoryError('model summarizer returned an invalid candidate')
        self._validate_provenance(candidate, snapshot)
        if (
            self.policy_revision_reader is not None
            and self.policy_revision_reader() != snapshot.policy_revision
        ):
            raise CompactMemoryError('candidate policy revision changed during generation')
        self.store.save(candidate)
        self.state = candidate
        return candidate

    @staticmethod
    def _validate_provenance(
        candidate: ModelCompactMemoryCandidate,
        snapshot: EffectiveMemorySnapshot,
    ) -> None:
        if candidate.source_policy_revision != snapshot.policy_revision:
            raise CompactMemoryError('candidate policy revision is stale')
        sources = {turn.turn_id: turn for turn in snapshot.turns}
        for claim in candidate.claims:
            referenced_content = []
            for turn_id, policy_id in zip(
                claim.source_turn_ids,
                claim.source_policy_ids,
                strict=True,
            ):
                source = sources.get(turn_id)
                if source is None:
                    raise CompactMemoryError('claim source does not exist')
                if not source.completed_exchange:
                    raise CompactMemoryError('claim references incomplete exchange')
                if source.forgotten or source.content is None:
                    raise CompactMemoryError('claim references forgotten source')
                if source.source_policy_id != policy_id:
                    raise CompactMemoryError('claim source policy is stale')
                referenced_content.append(_normalized_content(source.content))
            if _normalized_content(claim.text) not in referenced_content:
                raise CompactMemoryError('unsupported claim')


class ModelCompactSummarizer:
    def __init__(
        self,
        brain,
        model: str,
        clock: Callable[[], datetime] | None = None,
    ):
        self.brain = brain
        self.model = model
        self.version = f'model-v1:{model}'
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def __call__(
        self,
        snapshot: EffectiveMemorySnapshot,
    ) -> ModelCompactMemoryCandidate:
        effective_turns = [
            {
                'turn_id': turn.turn_id,
                'role': turn.role,
                'content': turn.content,
                'source_policy_id': turn.source_policy_id,
            }
            for turn in snapshot.turns
            if not turn.forgotten and turn.content is not None
        ]
        generated_at = self.clock()
        if generated_at.tzinfo is None:
            raise CompactMemoryError('model summarizer clock must be timezone-aware')
        request = {
            'generated_at_utc': generated_at.astimezone(timezone.utc).isoformat(),
            'source_policy_revision': snapshot.policy_revision,
            'summarizer': self.version,
            'effective_turns': effective_turns,
        }
        messages = [
            {
                'role': 'system',
                'content': (
                    'Return JSON only. Extract only explicit claims by copying '
                    'their complete source content exactly. Never infer, combine, '
                    'or paraphrase. Use summary_version 1 and the supplied '
                    'summarizer and source_policy_revision. Each claim requires a '
                    'unique claim_id, one or more source_turn_ids, corresponding '
                    'source_policy_ids, confidence, status "explicit", '
                    'generated_at_utc, and summarizer. Return an empty claims '
                    'array when no explicit claim is suitable.'
                ),
            },
            {
                'role': 'user',
                'content': json.dumps(request, ensure_ascii=True, sort_keys=True),
            },
        ]
        return replace(
            parse_model_candidate(self.brain.chat(messages)),
            provider='local',
            model=self.model,
        )


class ProviderBackedCompactSummarizer(ModelCompactSummarizer):
    def __init__(self, provider, clock: Callable[[], datetime] | None = None):
        super().__init__(provider, provider.model_id, clock)
        self.provider = provider
        self.version = f'model-v2:{provider.provider_id}:{provider.model_id}'
        self.last_generation = None

    def __call__(
        self,
        snapshot: EffectiveMemorySnapshot,
    ) -> ModelCompactMemoryCandidate:
        self.last_generation = None
        health = self.provider.health()
        if not health.get('ok'):
            raise SummarizerProviderError(
                f'provider unavailable: {health.get("error", "health check failed")}'
            )
        messages, schema = self._request(snapshot)
        generation = self.provider.generate(messages, schema)
        self.last_generation = generation
        if (
            generation.provider != self.provider.provider_id
            or generation.model != self.provider.model_id
        ):
            raise CompactMemoryError('provider identity mismatch')
        candidate = parse_model_candidate(generation.content)
        if candidate.summarizer != self.version:
            raise CompactMemoryError('candidate summarizer provenance is stale')
        return replace(
            candidate,
            provider=generation.provider,
            model=generation.model,
        )

    def _request(self, snapshot: EffectiveMemorySnapshot) -> tuple[list[dict], dict]:
        effective_turns = [
            {
                'turn_id': turn.turn_id,
                'role': turn.role,
                'content': turn.content,
                'source_policy_id': turn.source_policy_id,
            }
            for turn in snapshot.turns
            if not turn.forgotten and turn.content is not None
        ]
        generated_at = self.clock()
        if generated_at.tzinfo is None:
            raise CompactMemoryError('model summarizer clock must be timezone-aware')
        request = {
            'generated_at_utc': generated_at.astimezone(timezone.utc).isoformat(),
            'source_policy_revision': snapshot.policy_revision,
            'summarizer': self.version,
            'effective_turns': effective_turns,
        }
        messages = [
            {
                'role': 'system',
                'content': (
                    'Extract only explicit claims by copying their complete source '
                    'content exactly. Never infer, combine, or paraphrase. Use the '
                    'supplied metadata. Return an empty claims array when no explicit '
                    'claim is suitable.'
                ),
            },
            {'role': 'user', 'content': json.dumps(request, ensure_ascii=True, sort_keys=True)},
        ]
        return messages, _model_candidate_json_schema()


def _model_candidate_json_schema() -> dict:
    claim = {
        'type': 'object',
        'properties': {
            'claim_id': {'type': 'string'},
            'text': {'type': 'string'},
            'source_turn_ids': {'type': 'array', 'items': {'type': 'string'}},
            'source_policy_ids': {
                'type': 'array',
                'items': {'type': ['string', 'null']},
            },
            'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
            'status': {'type': 'string', 'enum': ['explicit']},
            'generated_at_utc': {'type': 'string'},
            'summarizer': {'type': 'string'},
        },
        'required': [
            'claim_id', 'text', 'source_turn_ids', 'source_policy_ids',
            'confidence', 'status', 'generated_at_utc', 'summarizer',
        ],
        'additionalProperties': False,
    }
    return {
        'type': 'object',
        'properties': {
            'summary_version': {'type': 'integer', 'enum': [1]},
            'generated_at_utc': {'type': 'string'},
            'summarizer': {'type': 'string'},
            'source_policy_revision': {'type': 'integer', 'minimum': 0},
            'claims': {'type': 'array', 'items': claim},
        },
        'required': [
            'summary_version', 'generated_at_utc', 'summarizer',
            'source_policy_revision', 'claims',
        ],
        'additionalProperties': False,
    }


@dataclass(frozen=True)
class CompactEvaluationReport:
    generated_at_utc: str
    checkpoint: int | None
    source_policy_revision: int
    baseline_summary_version: int
    baseline_summarizer: str
    baseline_output: list[dict]
    candidate_output: list[dict]
    baseline_claim_count: int
    candidate_claim_count: int
    shared_claim_count: int
    baseline_only_claim_count: int
    candidate_only_claim_count: int
    unsupported_claim_count: int
    unsupported_claim_rate: float
    contradiction_rate: float
    inferred_claim_count: int
    provenance_failure_count: int
    factual_coverage: float
    provenance_coverage: float
    compression_ratio: float
    stale_claim_rate: float
    correction_adherence: float
    forgetting_adherence: float
    latency_seconds: float
    token_cost: int | None
    storage_bytes: int
    accepted: bool
    rejection_reason: str | None


class CompactEvaluationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[CompactEvaluationReport]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(payload, list):
                raise TypeError
            return [CompactEvaluationReport(**item) for item in payload]
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CompactMemoryError('compact evaluation history is malformed') from exc

    def append(self, report: CompactEvaluationReport) -> None:
        reports = self.load()
        reports.append(report)
        temporary_path = self.path.with_suffix(f'{self.path.suffix}.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary_path.open('w', encoding='utf-8', newline='\n') as stream:
                json.dump([asdict(item) for item in reports], stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(self.path)
        except OSError as exc:
            raise CompactMemoryError('could not save compact evaluation') from exc
        finally:
            temporary_path.unlink(missing_ok=True)


class CompactMemoryEvaluator:
    def __init__(
        self,
        manager: ModelCompactMemoryManager,
        report_store: CompactEvaluationStore,
        clock: Callable[[], datetime] | None = None,
        max_source_characters: int = 2000,
    ):
        if max_source_characters < 100:
            raise ValueError('max_source_characters must be at least 100')
        self.manager = manager
        self.report_store = report_store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_source_characters = max_source_characters

    def update(
        self,
        snapshot: EffectiveMemorySnapshot,
        checkpoint: int | None = None,
    ) -> CompactEvaluationReport:
        snapshot = _bounded_effective_snapshot(snapshot, self.max_source_characters)
        baseline = {
            _normalized_content(turn.content)
            for turn in snapshot.turns
            if not turn.forgotten and turn.content is not None
        }
        started = time.perf_counter()
        candidate = None
        rejection_reason = None
        try:
            candidate = self.manager.update(snapshot)
        except CompactMemoryError as exc:
            rejection_reason = str(exc)
        latency = time.perf_counter() - started
        candidate_texts = {
            _normalized_content(claim.text)
            for claim in (candidate.claims if candidate is not None else ())
        }
        shared = baseline & candidate_texts
        unsupported = candidate_texts - baseline
        candidate_count = len(candidate_texts)
        baseline_output = [
            {
                'text': _normalized_content(turn.content),
                'source_turn_ids': [turn.turn_id],
                'source_policy_ids': [turn.source_policy_id],
            }
            for turn in snapshot.turns
            if not turn.forgotten and turn.content is not None
        ]
        candidate_output = (
            [
                {
                    **asdict(claim),
                    'source_turn_ids': list(claim.source_turn_ids),
                    'source_policy_ids': list(claim.source_policy_ids),
                }
                for claim in candidate.claims
            ]
            if candidate is not None else []
        )
        unsupported_count = len(unsupported) + int(
            rejection_reason == 'unsupported claim'
        )
        source_characters = sum(len(text) for text in baseline)
        candidate_characters = sum(len(text) for text in candidate_texts)
        report = CompactEvaluationReport(
            generated_at_utc=self._timestamp(),
            checkpoint=checkpoint,
            source_policy_revision=snapshot.policy_revision,
            baseline_summary_version=COMPACT_MEMORY_SCHEMA_VERSION,
            baseline_summarizer=ExtractiveCompactSummarizer.version,
            baseline_output=baseline_output,
            candidate_output=candidate_output,
            baseline_claim_count=len(baseline),
            candidate_claim_count=candidate_count,
            shared_claim_count=len(shared),
            baseline_only_claim_count=len(baseline - candidate_texts),
            candidate_only_claim_count=len(candidate_texts - baseline),
            unsupported_claim_count=unsupported_count,
            unsupported_claim_rate=(
                unsupported_count / max(candidate_count, unsupported_count, 1)
            ),
            contradiction_rate=(
                unsupported_count / max(candidate_count, unsupported_count, 1)
            ),
            inferred_claim_count=sum(
                claim.status == 'inferred'
                for claim in (candidate.claims if candidate is not None else ())
            ),
            provenance_failure_count=int(
                rejection_reason is not None
                and any(word in rejection_reason for word in ('source', 'policy'))
            ),
            factual_coverage=len(shared) / len(baseline) if baseline else 1.0,
            provenance_coverage=1.0 if candidate is not None else 0.0,
            compression_ratio=(
                candidate_characters / source_characters if source_characters else 0.0
            ),
            stale_claim_rate=0.0 if candidate is not None else 1.0,
            correction_adherence=1.0 if candidate is not None else 0.0,
            forgetting_adherence=1.0 if candidate is not None else 0.0,
            latency_seconds=latency,
            token_cost=None,
            storage_bytes=len(json.dumps(asdict(candidate))) if candidate else 0,
            accepted=candidate is not None,
            rejection_reason=rejection_reason,
        )
        self.report_store.append(report)
        return report

    def _timestamp(self) -> str:
        timestamp = self.clock()
        if timestamp.tzinfo is None:
            raise CompactMemoryError('compact evaluation clock must be timezone-aware')
        return timestamp.astimezone(timezone.utc).isoformat()


def _bounded_effective_snapshot(
    snapshot: EffectiveMemorySnapshot,
    max_characters: int,
) -> EffectiveMemorySnapshot:
    retained = []
    retained_characters = 0
    for turn in reversed(snapshot.turns):
        if turn.forgotten or turn.content is None:
            continue
        source_characters = len(turn.content)
        if retained and retained_characters + source_characters > max_characters:
            break
        if source_characters > max_characters:
            continue
        retained.append(turn)
        retained_characters += source_characters
    return EffectiveMemorySnapshot(
        policy_revision=snapshot.policy_revision,
        turns=tuple(reversed(retained)),
    )


class ModelCompactMemoryWorker:
    def __init__(self, evaluator: CompactMemoryEvaluator, logger):
        self.evaluator = evaluator
        self.logger = logger
        self.jobs = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(
            target=self._run,
            name='joi-model-compact-memory',
            daemon=True,
        )
        self.thread.start()

    def submit(self, snapshot: EffectiveMemorySnapshot) -> None:
        if self.closed:
            raise CompactMemoryError('model compact memory worker is closed')
        self.jobs.put(snapshot)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.jobs.put(None)
        self.jobs.join()
        self.thread.join()

    def _run(self) -> None:
        while True:
            snapshot = self.jobs.get()
            try:
                if snapshot is None:
                    return
                report = self.evaluator.update(snapshot)
                self.logger.info(
                    'Model compact shadow evaluated: accepted=%s claims=%d '
                    'coverage=%.3f revision=%d',
                    report.accepted,
                    report.candidate_claim_count,
                    report.factual_coverage,
                    report.source_policy_revision,
                )
            except Exception:
                self.logger.exception('Model compact shadow update failed')
            finally:
                self.jobs.task_done()


def _source_from_turn(turn: EpisodicTurn) -> CompactSource:
    return CompactSource(
        turn_id=turn.turn_id,
        role=turn.role,
        content=_normalized_content(turn.content),
    )


class ExtractiveCompactSummarizer:
    version = 'extractive-v1'

    def __init__(self, max_characters: int = 2000):
        if max_characters < 100:
            raise ValueError('max_characters must be at least 100')
        self.max_characters = max_characters

    def __call__(
        self,
        previous: CompactMemoryState | None,
        turns: Sequence[EpisodicTurn],
    ) -> CompactMemoryDraft:
        new_sources = tuple(_source_from_turn(turn) for turn in turns)
        if not new_sources:
            raise CompactMemoryError('compact memory requires source turns')

        retained = list(new_sources)
        retained_length = len('\n'.join(source.render() for source in retained))
        if retained_length > self.max_characters:
            raise CompactMemoryError('latest exchange exceeds compact memory limit')

        previous_sources = previous.sources if previous is not None else ()
        seen_ids = {source.turn_id for source in new_sources}
        for source in reversed(previous_sources):
            if source.turn_id in seen_ids:
                continue
            candidate = [source, *retained]
            if len('\n'.join(item.render() for item in candidate)) > self.max_characters:
                break
            retained = candidate
            seen_ids.add(source.turn_id)
        return CompactMemoryDraft(sources=tuple(retained))


class CompactMemoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> CompactMemoryState | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            return self._state_from_payload(payload)
        except CompactMemoryError:
            raise
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CompactMemoryError('compact memory is malformed') from exc

    def save(self, state: CompactMemoryState) -> None:
        self._validate_state(state)
        temporary_path = self.path.with_suffix(f'{self.path.suffix}.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = asdict(state)
            with temporary_path.open('w', encoding='utf-8', newline='\n') as stream:
                json.dump(payload, stream, ensure_ascii=True, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(self.path)
        except OSError as exc:
            raise CompactMemoryError('could not save compact memory') from exc
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _state_from_payload(payload) -> CompactMemoryState:
        try:
            sources = tuple(CompactSource(**source) for source in payload['sources'])
            state = CompactMemoryState(
                summary=payload['summary'],
                sources=sources,
                source_turn_ids=tuple(payload['source_turn_ids']),
                updated_at_utc=payload['updated_at_utc'],
                summarizer_version=payload['summarizer_version'],
                schema_version=payload['schema_version'],
            )
        except (KeyError, TypeError) as exc:
            raise CompactMemoryError('compact memory is malformed') from exc
        CompactMemoryStore._validate_state(state)
        return state

    @staticmethod
    def _validate_state(state: CompactMemoryState) -> None:
        if state.schema_version != COMPACT_MEMORY_SCHEMA_VERSION:
            raise CompactMemoryError(
                f'unsupported compact memory schema version: {state.schema_version}'
            )
        if not state.sources or not state.summarizer_version:
            raise CompactMemoryError('compact memory is malformed')
        expected_summary = '\n'.join(source.render() for source in state.sources)
        expected_ids = tuple(source.turn_id for source in state.sources)
        if state.summary != expected_summary or state.source_turn_ids != expected_ids:
            raise CompactMemoryError('compact memory is malformed')
        if len(set(expected_ids)) != len(expected_ids):
            raise CompactMemoryError('compact memory is malformed')
        if any(
            not source.turn_id
            or source.role not in {'user', 'assistant'}
            or not source.content
            for source in state.sources
        ):
            raise CompactMemoryError('compact memory is malformed')
        try:
            timestamp = datetime.fromisoformat(state.updated_at_utc)
        except (TypeError, ValueError) as exc:
            raise CompactMemoryError('compact memory is malformed') from exc
        if timestamp.tzinfo is None:
            raise CompactMemoryError('compact memory is malformed')


class CompactMemoryManager:
    def __init__(
        self,
        store: CompactMemoryStore,
        summarizer: CompactSummarizer,
        clock: Callable[[], datetime] | None = None,
    ):
        self.store = store
        self.summarizer = summarizer
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.state = store.load()

    def update(self, turns: Sequence[EpisodicTurn]) -> CompactMemoryState:
        turns = tuple(turns)
        if not turns or len({turn.turn_id for turn in turns}) != len(turns):
            raise CompactMemoryError('compact memory requires unique source turns')
        known_sources = {
            source.turn_id: source
            for source in (self.state.sources if self.state is not None else ())
        }
        known_sources.update((turn.turn_id, _source_from_turn(turn)) for turn in turns)

        try:
            draft = self.summarizer(self.state, turns)
        except CompactMemoryError:
            raise
        except Exception as exc:
            raise CompactMemoryError('summarizer failed') from exc
        if not isinstance(draft, CompactMemoryDraft):
            raise CompactMemoryError('summarizer returned an invalid draft')
        if not draft.sources:
            raise CompactMemoryError('summarizer returned an invalid draft')
        try:
            version = self.summarizer.version
        except (AttributeError, TypeError) as exc:
            raise CompactMemoryError('summarizer returned an invalid draft') from exc

        draft_ids = {source.turn_id for source in draft.sources}
        new_ids = {turn.turn_id for turn in turns}
        if not new_ids.issubset(draft_ids):
            raise CompactMemoryError('summarizer dropped current source turns')
        if any(known_sources.get(source.turn_id) != source for source in draft.sources):
            raise CompactMemoryError('summarizer contradicted source excerpts')

        timestamp = self.clock()
        if timestamp.tzinfo is None:
            raise CompactMemoryError('compact memory clock must be timezone-aware')
        summary = '\n'.join(source.render() for source in draft.sources)
        candidate = CompactMemoryState(
            summary=summary,
            sources=draft.sources,
            source_turn_ids=tuple(source.turn_id for source in draft.sources),
            updated_at_utc=timestamp.astimezone(timezone.utc).isoformat(),
            summarizer_version=version,
        )
        self.store.save(candidate)
        self.state = candidate
        return candidate


class CompactMemoryWorker:
    def __init__(self, manager: CompactMemoryManager, logger):
        self.manager = manager
        self.logger = logger
        self.jobs = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(
            target=self._run,
            name='joi-compact-memory',
            daemon=True,
        )
        self.thread.start()

    def submit(self, turns: Sequence[EpisodicTurn]) -> None:
        if self.closed:
            raise CompactMemoryError('compact memory worker is closed')
        self.jobs.put(tuple(turns))

    def wait_for_idle(self) -> None:
        self.jobs.join()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.jobs.put(None)
        self.jobs.join()
        self.thread.join()

    def _run(self) -> None:
        while True:
            turns = self.jobs.get()
            try:
                if turns is None:
                    return
                state = self.manager.update(turns)
                self.logger.info(
                    'Compact memory shadow updated: sources=%d version=%s',
                    len(state.source_turn_ids),
                    state.summarizer_version,
                )
            except Exception:
                self.logger.exception('Compact memory shadow update failed')
            finally:
                self.jobs.task_done()
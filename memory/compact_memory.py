import json
import os
import queue
import threading
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from memory.memory_store import EpisodicTurn


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


class CompactSummarizer(Protocol):
    version: str

    def __call__(
        self,
        previous: CompactMemoryState | None,
        turns: Sequence[EpisodicTurn],
    ) -> CompactMemoryDraft: ...


def _normalized_content(content: str) -> str:
    return ' '.join(content.split())


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
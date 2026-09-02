import hashlib
import json
import os
import queue
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Protocol, Sequence

from memory.memory_store import EpisodicTurn, MemoryPolicyRecord


GRAPH_SCHEMA_VERSION = 1
ENTITY_TYPES = frozenset({
    'person',
    'project',
    'concept',
    'place',
    'preference',
    'fact',
    'task_topic',
})


class GraphMemoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphEvidenceRef:
    exchange_id: str
    turn_ids: tuple[str, ...]
    policy_ids: tuple[str | None, ...]
    observed_at_utc: str
    suppressed: bool


@dataclass(frozen=True)
class EntityCandidate:
    entity_id: str
    canonical_label: str
    surface_form: str
    entity_type: str
    evidence: GraphEvidenceRef
    extractor_version: str
    status: str


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    canonical_label: str
    entity_type: str
    aliases: tuple[str, ...]
    source_refs: tuple[GraphEvidenceRef, ...]
    first_seen_utc: str
    last_seen_utc: str
    observation_count: int
    schema_version: int = GRAPH_SCHEMA_VERSION


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    weight: int
    source_exchange_ids: tuple[str, ...]
    first_seen_utc: str
    last_seen_utc: str
    schema_version: int = GRAPH_SCHEMA_VERSION


@dataclass(frozen=True)
class GraphState:
    extractor_version: str
    processed_exchange_ids: tuple[str, ...]
    nodes: dict[str, GraphNode]
    edges: dict[str, GraphEdge]
    updated_at_utc: str
    schema_version: int = GRAPH_SCHEMA_VERSION


@dataclass(frozen=True)
class GraphUpdateAudit:
    exchange_id: str
    extracted_entity_count: int
    accepted_entity_count: int
    rejected_entity_count: int
    node_create_count: int
    node_update_count: int
    edge_create_count: int
    edge_update_count: int
    rejection_reasons: tuple[str, ...]
    write_latency_seconds: float
    extractor_version: str
    schema_version: int = GRAPH_SCHEMA_VERSION


class EntityExtractor(Protocol):
    version: str

    def extract(self, turns: Sequence[EpisodicTurn]) -> tuple[EntityCandidate, ...]: ...


def _canonical_label(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def _has_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def build_entity_id(entity_type: str, label: str) -> str:
    if entity_type not in ENTITY_TYPES:
        raise GraphMemoryError('unsupported entity type')
    canonical_label = _canonical_label(label)
    if not canonical_label or _has_surrogate(canonical_label):
        raise GraphMemoryError('entity label is malformed')
    digest = hashlib.sha256(
        f'{entity_type}\x00{canonical_label}'.encode('utf-8')
    ).hexdigest()[:24]
    return f'entity-{digest}'


def _build_edge_id(source_node_id: str, target_node_id: str) -> str:
    digest = hashlib.sha256(
        f'co_occurs\x00{source_node_id}\x00{target_node_id}'.encode('ascii')
    ).hexdigest()[:24]
    return f'edge-{digest}'


def _require_utc(value: str) -> None:
    try:
        timestamp = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise GraphMemoryError('graph timestamp is malformed') from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise GraphMemoryError('graph timestamp is malformed')


def _evidence_sort_key(evidence: GraphEvidenceRef):
    return (
        evidence.exchange_id,
        evidence.turn_ids,
        tuple(policy or '' for policy in evidence.policy_ids),
        evidence.observed_at_utc,
        evidence.suppressed,
    )


class ExplicitEntityExtractor:
    version = 'explicit-patterns-v1'
    _patterns = (
        ('person', re.compile(
            r'\bmy name is\s+([^\W\d_][\w\'-]*(?:\s+[^\W\d_][\w\'-]*){0,3})',
            re.IGNORECASE,
        )),
        ('project', re.compile(
            r"\b(?:(?:i am|i'm|we are|we're) working on|(?:my|our) project is)\s+([^.!?\n]{1,80})",
            re.IGNORECASE,
        )),
        ('concept', re.compile(
            r"\b(?:we are discussing|we discussed|let's discuss)\s+([^.!?\n]{1,80})",
            re.IGNORECASE,
        )),
        ('place', re.compile(
            r'\bi live in\s+([^.!?\n]{1,80})',
            re.IGNORECASE,
        )),
        ('preference', re.compile(
            r'\bi prefer\s+([^.!?\n]{1,80})',
            re.IGNORECASE,
        )),
        ('fact', re.compile(
            r'\bremember that\s+([^.!?\n]{1,80})',
            re.IGNORECASE,
        )),
        ('task_topic', re.compile(
            r'\b(?:the|my|our) (?:current |next )?task is\s+([^.!?\n]{1,80})',
            re.IGNORECASE,
        )),
    )

    def extract(self, turns: Sequence[EpisodicTurn]) -> tuple[EntityCandidate, ...]:
        turns = _validated_exchange(turns)
        candidates: dict[str, EntityCandidate] = {}
        for turn in turns:
            if _has_surrogate(turn.content):
                raise GraphMemoryError('source content is malformed')
            for entity_type, pattern in self._patterns:
                for match in pattern.finditer(turn.content):
                    surface_form = match.group(1).strip()
                    canonical_label = _canonical_label(surface_form)
                    entity_id = build_entity_id(entity_type, canonical_label)
                    candidates.setdefault(entity_id, EntityCandidate(
                        entity_id=entity_id,
                        canonical_label=canonical_label,
                        surface_form=surface_form,
                        entity_type=entity_type,
                        evidence=GraphEvidenceRef(
                            exchange_id=turn.exchange_id,
                            turn_ids=(turn.turn_id,),
                            policy_ids=(None,),
                            observed_at_utc=turn.created_at_utc,
                            suppressed=False,
                        ),
                        extractor_version=self.version,
                        status='explicit',
                    ))
        return tuple(sorted(
            candidates.values(),
            key=lambda candidate: (candidate.entity_type, candidate.entity_id),
        ))


def _validated_exchange(turns: Sequence[EpisodicTurn]) -> tuple[EpisodicTurn, ...]:
    turns = tuple(turns)
    if len(turns) != 2:
        raise GraphMemoryError('graph update requires one completed exchange')
    if tuple(turn.role for turn in turns) != ('user', 'assistant'):
        raise GraphMemoryError('graph update requires ordered user and assistant turns')
    if len({turn.turn_id for turn in turns}) != 2:
        raise GraphMemoryError('graph update requires unique source turns')
    if len({turn.exchange_id for turn in turns}) != 1:
        raise GraphMemoryError('graph update requires one completed exchange')
    for turn in turns:
        if not turn.turn_id or not turn.exchange_id or not turn.content.strip():
            raise GraphMemoryError('graph source turn is malformed')
        _require_utc(turn.created_at_utc)
    return turns


class GraphMemoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> GraphState | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            state = _state_from_payload(payload)
            _validate_state(state)
            return state
        except GraphMemoryError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise GraphMemoryError('graph artifact is malformed') from exc

    def save(self, state: GraphState) -> None:
        _validate_state(state)
        payload = _state_to_payload(state)
        temporary_path = self.path.with_suffix(f'{self.path.suffix}.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ) + '\n',
                encoding='utf-8',
            )
            os.replace(temporary_path, self.path)
        except (OSError, UnicodeError) as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise GraphMemoryError('could not save graph artifact') from exc


def _state_to_payload(state: GraphState) -> dict:
    return {
        'schema_version': state.schema_version,
        'extractor_version': state.extractor_version,
        'processed_exchange_ids': list(state.processed_exchange_ids),
        'nodes': {
            node_id: {
                **asdict(node),
                'aliases': list(node.aliases),
                'source_refs': [asdict(source) for source in node.source_refs],
            }
            for node_id, node in sorted(state.nodes.items())
        },
        'edges': {
            edge_id: {
                **asdict(edge),
                'source_exchange_ids': list(edge.source_exchange_ids),
            }
            for edge_id, edge in sorted(state.edges.items())
        },
        'updated_at_utc': state.updated_at_utc,
    }


def _state_from_payload(payload: dict) -> GraphState:
    required = {
        'schema_version',
        'extractor_version',
        'processed_exchange_ids',
        'nodes',
        'edges',
        'updated_at_utc',
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise GraphMemoryError('graph artifact is malformed')
    if payload['schema_version'] != GRAPH_SCHEMA_VERSION:
        raise GraphMemoryError('unsupported graph schema version')
    if not isinstance(payload['nodes'], dict) or not isinstance(payload['edges'], dict):
        raise GraphMemoryError('graph artifact is malformed')
    nodes = {
        node_id: _node_from_payload(node_payload)
        for node_id, node_payload in payload['nodes'].items()
    }
    edges = {
        edge_id: _edge_from_payload(edge_payload)
        for edge_id, edge_payload in payload['edges'].items()
    }
    return GraphState(
        extractor_version=payload['extractor_version'],
        processed_exchange_ids=tuple(payload['processed_exchange_ids']),
        nodes=nodes,
        edges=edges,
        updated_at_utc=payload['updated_at_utc'],
        schema_version=payload['schema_version'],
    )


def _node_from_payload(payload: dict) -> GraphNode:
    required = {
        'node_id',
        'canonical_label',
        'entity_type',
        'aliases',
        'source_refs',
        'first_seen_utc',
        'last_seen_utc',
        'observation_count',
        'schema_version',
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise GraphMemoryError('graph artifact is malformed')
    return GraphNode(
        node_id=payload['node_id'],
        canonical_label=payload['canonical_label'],
        entity_type=payload['entity_type'],
        aliases=tuple(payload['aliases']),
        source_refs=tuple(_evidence_from_payload(item) for item in payload['source_refs']),
        first_seen_utc=payload['first_seen_utc'],
        last_seen_utc=payload['last_seen_utc'],
        observation_count=payload['observation_count'],
        schema_version=payload['schema_version'],
    )


def _edge_from_payload(payload: dict) -> GraphEdge:
    required = {
        'edge_id',
        'source_node_id',
        'target_node_id',
        'relation',
        'weight',
        'source_exchange_ids',
        'first_seen_utc',
        'last_seen_utc',
        'schema_version',
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise GraphMemoryError('graph artifact is malformed')
    return GraphEdge(
        edge_id=payload['edge_id'],
        source_node_id=payload['source_node_id'],
        target_node_id=payload['target_node_id'],
        relation=payload['relation'],
        weight=payload['weight'],
        source_exchange_ids=tuple(payload['source_exchange_ids']),
        first_seen_utc=payload['first_seen_utc'],
        last_seen_utc=payload['last_seen_utc'],
        schema_version=payload['schema_version'],
    )


def _evidence_from_payload(payload: dict) -> GraphEvidenceRef:
    required = {
        'exchange_id',
        'turn_ids',
        'policy_ids',
        'observed_at_utc',
        'suppressed',
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise GraphMemoryError('graph artifact is malformed')
    return GraphEvidenceRef(
        exchange_id=payload['exchange_id'],
        turn_ids=tuple(payload['turn_ids']),
        policy_ids=tuple(payload['policy_ids']),
        observed_at_utc=payload['observed_at_utc'],
        suppressed=payload['suppressed'],
    )


def _validate_evidence(evidence: GraphEvidenceRef) -> None:
    if (
        not isinstance(evidence.exchange_id, str)
        or not evidence.exchange_id
        or not evidence.turn_ids
        or any(not isinstance(turn_id, str) or not turn_id for turn_id in evidence.turn_ids)
        or len(set(evidence.turn_ids)) != len(evidence.turn_ids)
        or len(evidence.policy_ids) != len(evidence.turn_ids)
        or any(policy is not None and (not isinstance(policy, str) or not policy)
               for policy in evidence.policy_ids)
        or not isinstance(evidence.suppressed, bool)
    ):
        raise GraphMemoryError('graph evidence is malformed')
    _require_utc(evidence.observed_at_utc)


def _validate_state(state: GraphState) -> None:
    if state.schema_version != GRAPH_SCHEMA_VERSION:
        raise GraphMemoryError('unsupported graph schema version')
    if not isinstance(state.extractor_version, str) or not state.extractor_version:
        raise GraphMemoryError('graph artifact is malformed')
    if (
        tuple(sorted(set(state.processed_exchange_ids))) != state.processed_exchange_ids
        or any(not isinstance(item, str) or not item for item in state.processed_exchange_ids)
    ):
        raise GraphMemoryError('graph artifact is malformed')
    _require_utc(state.updated_at_utc)
    if set(state.nodes) != {node.node_id for node in state.nodes.values()}:
        raise GraphMemoryError('graph node key mismatch')
    if set(state.edges) != {edge.edge_id for edge in state.edges.values()}:
        raise GraphMemoryError('graph edge key mismatch')
    for node in state.nodes.values():
        if (
            node.schema_version != GRAPH_SCHEMA_VERSION
            or node.entity_type not in ENTITY_TYPES
            or node.node_id != build_entity_id(node.entity_type, node.canonical_label)
            or node.canonical_label != _canonical_label(node.canonical_label)
            or tuple(sorted(set(node.aliases))) != node.aliases
            or not node.aliases
            or tuple(sorted(set(node.source_refs), key=_evidence_sort_key)) != node.source_refs
            or not node.source_refs
            or node.observation_count != len({
                source.exchange_id for source in node.source_refs
            })
        ):
            raise GraphMemoryError('graph node is malformed')
        _require_utc(node.first_seen_utc)
        _require_utc(node.last_seen_utc)
        for source in node.source_refs:
            _validate_evidence(source)
    for edge in state.edges.values():
        expected_nodes = tuple(sorted((edge.source_node_id, edge.target_node_id)))
        source_node = state.nodes.get(edge.source_node_id)
        target_node = state.nodes.get(edge.target_node_id)
        source_evidence = {
            source.exchange_id
            for source in (source_node.source_refs if source_node is not None else ())
        }
        target_evidence = {
            source.exchange_id
            for source in (target_node.source_refs if target_node is not None else ())
        }
        if (
            edge.schema_version != GRAPH_SCHEMA_VERSION
            or edge.relation != 'co_occurs'
            or edge.source_node_id == edge.target_node_id
            or (edge.source_node_id, edge.target_node_id) != expected_nodes
            or edge.source_node_id not in state.nodes
            or edge.target_node_id not in state.nodes
            or edge.edge_id != _build_edge_id(*expected_nodes)
            or tuple(sorted(set(edge.source_exchange_ids))) != edge.source_exchange_ids
            or not edge.source_exchange_ids
            or edge.weight != len(edge.source_exchange_ids)
            or not set(edge.source_exchange_ids).issubset(
                source_evidence & target_evidence
            )
        ):
            raise GraphMemoryError('graph edge is malformed')
        _require_utc(edge.first_seen_utc)
        _require_utc(edge.last_seen_utc)


class GraphMemoryManager:
    def __init__(self, store: GraphMemoryStore, extractor: EntityExtractor):
        self.store = store
        self.extractor = extractor
        self.state = store.load()
        self.last_audit: GraphUpdateAudit | None = None
        if self.state is not None and self.state.extractor_version != extractor.version:
            raise GraphMemoryError('graph extractor version mismatch')

    def update(self, turns: Sequence[EpisodicTurn]) -> GraphState:
        started = time.perf_counter()
        turns = _validated_exchange(turns)
        exchange_id = turns[0].exchange_id
        if self.state is not None and exchange_id in self.state.processed_exchange_ids:
            self.last_audit = GraphUpdateAudit(
                exchange_id=exchange_id,
                extracted_entity_count=0,
                accepted_entity_count=0,
                rejected_entity_count=0,
                node_create_count=0,
                node_update_count=0,
                edge_create_count=0,
                edge_update_count=0,
                rejection_reasons=(),
                write_latency_seconds=time.perf_counter() - started,
                extractor_version=self.extractor.version,
            )
            return self.state
        candidates = ()
        try:
            candidates = tuple(self.extractor.extract(turns))
            self._validate_candidates(candidates, turns)
        except GraphMemoryError as exc:
            self._record_rejection(exchange_id, candidates, str(exc), started)
            raise
        except Exception as exc:
            self._record_rejection(
                exchange_id,
                candidates,
                'graph extractor failed',
                started,
            )
            raise GraphMemoryError('graph extractor failed') from exc
        timestamp = max(turn.created_at_utc for turn in turns)
        nodes = dict(self.state.nodes) if self.state is not None else {}
        edges = dict(self.state.edges) if self.state is not None else {}
        node_create_count = sum(
            candidate.entity_id not in nodes for candidate in candidates
        )
        node_update_count = len(candidates) - node_create_count
        for candidate in candidates:
            existing = nodes.get(candidate.entity_id)
            source_refs = tuple(sorted(
                set((existing.source_refs if existing is not None else ()))
                | {candidate.evidence},
                key=_evidence_sort_key,
            ))
            nodes[candidate.entity_id] = GraphNode(
                node_id=candidate.entity_id,
                canonical_label=candidate.canonical_label,
                entity_type=candidate.entity_type,
                aliases=tuple(sorted(
                    set((existing.aliases if existing is not None else ()))
                    | {candidate.surface_form}
                )),
                source_refs=source_refs,
                first_seen_utc=(
                    min(existing.first_seen_utc, timestamp)
                    if existing is not None else timestamp
                ),
                last_seen_utc=(
                    max(existing.last_seen_utc, timestamp)
                    if existing is not None else timestamp
                ),
                observation_count=len({source.exchange_id for source in source_refs}),
            )
        candidate_ids = sorted({candidate.entity_id for candidate in candidates})
        candidate_pairs = tuple(combinations(candidate_ids, 2))
        edge_create_count = sum(
            _build_edge_id(*pair) not in edges for pair in candidate_pairs
        )
        edge_update_count = len(candidate_pairs) - edge_create_count
        for source_node_id, target_node_id in candidate_pairs:
            edge_id = _build_edge_id(source_node_id, target_node_id)
            existing = edges.get(edge_id)
            source_exchange_ids = tuple(sorted(
                set(existing.source_exchange_ids if existing is not None else ())
                | {exchange_id}
            ))
            edges[edge_id] = GraphEdge(
                edge_id=edge_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                relation='co_occurs',
                weight=len(source_exchange_ids),
                source_exchange_ids=source_exchange_ids,
                first_seen_utc=(
                    min(existing.first_seen_utc, timestamp)
                    if existing is not None else timestamp
                ),
                last_seen_utc=(
                    max(existing.last_seen_utc, timestamp)
                    if existing is not None else timestamp
                ),
            )
        processed = tuple(sorted(
            set(self.state.processed_exchange_ids if self.state is not None else ())
            | {exchange_id}
        ))
        candidate_state = GraphState(
            extractor_version=self.extractor.version,
            processed_exchange_ids=processed,
            nodes=nodes,
            edges=edges,
            updated_at_utc=timestamp,
        )
        try:
            self.store.save(candidate_state)
        except GraphMemoryError as exc:
            self._record_rejection(exchange_id, candidates, str(exc), started)
            raise
        self.state = candidate_state
        self.last_audit = GraphUpdateAudit(
            exchange_id=exchange_id,
            extracted_entity_count=len(candidates),
            accepted_entity_count=len(candidates),
            rejected_entity_count=0,
            node_create_count=node_create_count,
            node_update_count=node_update_count,
            edge_create_count=edge_create_count,
            edge_update_count=edge_update_count,
            rejection_reasons=(),
            write_latency_seconds=time.perf_counter() - started,
            extractor_version=self.extractor.version,
        )
        return candidate_state

    def _record_rejection(
        self,
        exchange_id: str,
        candidates: tuple[EntityCandidate, ...],
        reason: str,
        started: float,
    ) -> None:
        self.last_audit = GraphUpdateAudit(
            exchange_id=exchange_id,
            extracted_entity_count=len(candidates),
            accepted_entity_count=0,
            rejected_entity_count=len(candidates),
            node_create_count=0,
            node_update_count=0,
            edge_create_count=0,
            edge_update_count=0,
            rejection_reasons=(reason,),
            write_latency_seconds=time.perf_counter() - started,
            extractor_version=self.extractor.version,
        )

    def apply_policy(self, policy: MemoryPolicyRecord) -> GraphState | None:
        if self.state is None:
            return None
        changed = False
        nodes = {}
        for node_id, node in self.state.nodes.items():
            source_refs = []
            for source in node.source_refs:
                if policy.target_turn_id not in source.turn_ids:
                    source_refs.append(source)
                    continue
                policy_ids = tuple(
                    policy.policy_id if turn_id == policy.target_turn_id else policy_id
                    for turn_id, policy_id in zip(source.turn_ids, source.policy_ids)
                )
                source_refs.append(replace(
                    source,
                    policy_ids=policy_ids,
                    suppressed=True,
                ))
                changed = True
            nodes[node_id] = replace(
                node,
                source_refs=tuple(sorted(set(source_refs), key=_evidence_sort_key)),
            )
        if not changed:
            return self.state
        candidate_state = replace(
            self.state,
            nodes=nodes,
            updated_at_utc=policy.created_at_utc,
        )
        self.store.save(candidate_state)
        self.state = candidate_state
        return candidate_state

    def status(self) -> dict[str, int | str]:
        state = self.state
        if state is None:
            return {
                'schema_version': GRAPH_SCHEMA_VERSION,
                'extractor_version': self.extractor.version,
                'processed_exchange_count': 0,
                'node_count': 0,
                'edge_count': 0,
                'suppressed_source_count': 0,
            }
        return {
            'schema_version': state.schema_version,
            'extractor_version': state.extractor_version,
            'processed_exchange_count': len(state.processed_exchange_ids),
            'node_count': len(state.nodes),
            'edge_count': len(state.edges),
            'suppressed_source_count': sum(
                source.suppressed
                for node in state.nodes.values()
                for source in node.source_refs
            ),
        }

    def recent(self, limit: int = 10) -> list[GraphNode]:
        if limit <= 0 or limit > 100:
            raise ValueError('limit must be between 1 and 100')
        if self.state is None:
            return []
        return sorted(
            self.state.nodes.values(),
            key=lambda node: (node.last_seen_utc, node.node_id),
        )[-limit:]

    def why(self, item_id: str) -> GraphNode | GraphEdge:
        if self.state is not None:
            if item_id in self.state.nodes:
                return self.state.nodes[item_id]
            if item_id in self.state.edges:
                return self.state.edges[item_id]
        raise GraphMemoryError(f'graph item not found: {item_id}')

    def _validate_candidates(
        self,
        candidates: tuple[EntityCandidate, ...],
        turns: tuple[EpisodicTurn, ...],
    ) -> None:
        turn_by_id = {turn.turn_id: turn for turn in turns}
        seen = set()
        for candidate in candidates:
            if not isinstance(candidate, EntityCandidate):
                raise GraphMemoryError('extractor returned malformed candidate')
            if candidate.entity_id in seen:
                raise GraphMemoryError('extractor returned duplicate entity ID')
            seen.add(candidate.entity_id)
            if (
                candidate.entity_type not in ENTITY_TYPES
                or candidate.status != 'explicit'
                or candidate.extractor_version != self.extractor.version
                or candidate.canonical_label != _canonical_label(candidate.surface_form)
                or candidate.entity_id != build_entity_id(
                    candidate.entity_type,
                    candidate.canonical_label,
                )
            ):
                raise GraphMemoryError('extractor returned malformed candidate')
            _validate_evidence(candidate.evidence)
            if candidate.evidence.exchange_id != turns[0].exchange_id:
                raise GraphMemoryError('candidate provenance mismatch')
            if candidate.evidence.suppressed:
                raise GraphMemoryError('candidate provenance mismatch')
            for turn_id in candidate.evidence.turn_ids:
                source = turn_by_id.get(turn_id)
                if source is None:
                    raise GraphMemoryError('candidate provenance mismatch')
                if candidate.surface_form not in source.content:
                    raise GraphMemoryError('unsupported surface form')


class GraphMemoryWorker:
    def __init__(self, manager: GraphMemoryManager, logger):
        self.manager = manager
        self.logger = logger
        self.jobs = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(
            target=self._run,
            name='joi-graph-memory',
            daemon=True,
        )
        self.thread.start()

    def submit(self, turns: Sequence[EpisodicTurn]) -> None:
        if self.closed:
            raise GraphMemoryError('graph memory worker is closed')
        self.jobs.put(('exchange', tuple(turns)))

    def submit_policy(self, policy: MemoryPolicyRecord) -> None:
        if self.closed:
            raise GraphMemoryError('graph memory worker is closed')
        self.jobs.put(('policy', policy))

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
            job = self.jobs.get()
            try:
                if job is None:
                    return
                kind, payload = job
                if kind == 'exchange':
                    state = self.manager.update(payload)
                    audit = self.manager.last_audit
                    self.logger.info(
                        'Graph memory write: exchange=%s extracted=%d accepted=%d '
                        'rejected=%d node_creates=%d node_updates=%d '
                        'edge_creates=%d edge_updates=%d latency=%.6f '
                        'schema=%d extractor=%s',
                        audit.exchange_id,
                        audit.extracted_entity_count,
                        audit.accepted_entity_count,
                        audit.rejected_entity_count,
                        audit.node_create_count,
                        audit.node_update_count,
                        audit.edge_create_count,
                        audit.edge_update_count,
                        audit.write_latency_seconds,
                        audit.schema_version,
                        audit.extractor_version,
                    )
                else:
                    state = self.manager.apply_policy(payload)
                    self.logger.info(
                        'Graph memory policy applied: changed=%s action=%s',
                        state is not None,
                        payload.action,
                    )
            except GraphMemoryError as exc:
                if job is not None and job[0] == 'exchange':
                    exchange_id = job[1][0].exchange_id if job[1] else 'unknown'
                    self.logger.error(
                        'Graph memory update rejected: exchange=%s reason=%s',
                        exchange_id,
                        str(exc),
                    )
                else:
                    self.logger.error(
                        'Graph memory policy rejected: reason=%s',
                        str(exc),
                    )
            except Exception:
                self.logger.exception('Graph memory update failed')
            finally:
                self.jobs.task_done()

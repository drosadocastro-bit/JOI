import hashlib
import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from functools import cmp_to_key
from itertools import combinations

from memory.graph_memory import (
    ExplicitEntityExtractor,
    GraphEdge,
    GraphEvidenceRef,
    GraphMemoryError,
    GraphNode,
    GraphState,
    build_entity_id,
)
from memory.memory_store import EffectiveMemorySnapshot


PPR_DAMPING_FACTOR = 0.85
PPR_TOLERANCE = 1e-12
PPR_MAX_ITERATIONS = 100


@dataclass(frozen=True)
class ExplicitEntitySurface:
    entity_id: str
    canonical_label: str
    surface_form: str
    entity_type: str


_QUERY_PATTERNS = (
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
    ('place', re.compile(r'\bi live in\s+([^.!?\n]{1,80})', re.IGNORECASE)),
    ('preference', re.compile(r'\bi prefer\s+([^.!?\n]{1,80})', re.IGNORECASE)),
    ('fact', re.compile(r'\bremember that\s+([^.!?\n]{1,80})', re.IGNORECASE)),
    ('task_topic', re.compile(
        r'\b(?:the|my|our) (?:current |next )?task is\s+([^.!?\n]{1,80})',
        re.IGNORECASE,
    )),
)


def _canonical_label(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def extract_explicit_entity_surfaces(content: str) -> tuple[ExplicitEntitySurface, ...]:
    if not isinstance(content, str) or any(
        0xD800 <= ord(character) <= 0xDFFF for character in content
    ):
        raise GraphMemoryError('source content is malformed')
    surfaces = {}
    for entity_type, pattern in _QUERY_PATTERNS:
        for match in pattern.finditer(content):
            surface_form = match.group(1).strip()
            canonical_label = _canonical_label(surface_form)
            entity_id = build_entity_id(entity_type, canonical_label)
            surfaces.setdefault(entity_id, ExplicitEntitySurface(
                entity_id=entity_id,
                canonical_label=canonical_label,
                surface_form=surface_form,
                entity_type=entity_type,
            ))
    return tuple(sorted(
        surfaces.values(),
        key=lambda surface: (surface.entity_type, surface.entity_id),
    ))


@dataclass(frozen=True)
class GraphQueryExtraction:
    query_turn_id: str
    entities: tuple[ExplicitEntitySurface, ...]
    seed_entity_ids: tuple[str, ...]
    unresolved_surface_forms: tuple[str, ...]
    extractor_version: str


class GraphQueryExtractor:
    version = ExplicitEntityExtractor.version

    def extract(
        self,
        *,
        query_turn_id: str,
        content: str,
        state: GraphState | None,
    ) -> GraphQueryExtraction:
        if not isinstance(query_turn_id, str) or not query_turn_id:
            raise GraphMemoryError('query turn ID is malformed')
        entities = extract_explicit_entity_surfaces(content)
        node_ids = set(state.nodes) if state is not None else set()
        seeds = tuple(sorted(
            entity.entity_id
            for entity in entities
            if entity.entity_id in node_ids
        ))
        unresolved = tuple(
            entity.surface_form
            for entity in entities
            if entity.entity_id not in node_ids
        )
        return GraphQueryExtraction(
            query_turn_id=query_turn_id,
            entities=entities,
            seed_entity_ids=seeds,
            unresolved_surface_forms=unresolved,
            extractor_version=self.version,
        )


@dataclass(frozen=True)
class PolicyExclusion:
    node_id: str
    reason: str
    policy_ids: tuple[str, ...]


@dataclass(frozen=True)
class EffectiveGraphView:
    state: GraphState
    exclusions: tuple[PolicyExclusion, ...]
    policy_revision: int

    def exclusion_for(self, node_id: str) -> PolicyExclusion:
        for exclusion in self.exclusions:
            if exclusion.node_id == node_id:
                return exclusion
        raise GraphMemoryError(f'graph node has no policy exclusion: {node_id}')


class EffectiveGraphBuilder:
    def build(
        self,
        historical_state: GraphState,
        snapshot: EffectiveMemorySnapshot,
    ) -> EffectiveGraphView:
        surfaces_by_exchange: dict[str, dict[str, ExplicitEntitySurface]] = defaultdict(dict)
        evidence_by_node: dict[str, list[GraphEvidenceRef]] = defaultdict(list)
        aliases_by_node: dict[str, set[str]] = defaultdict(set)
        surface_by_node: dict[str, ExplicitEntitySurface] = {}
        effective_turn_by_id = {turn.turn_id: turn for turn in snapshot.turns}

        for turn in snapshot.turns:
            if turn.forgotten or not turn.completed_exchange or turn.content is None:
                continue
            for surface in extract_explicit_entity_surfaces(turn.content):
                surface_by_node.setdefault(surface.entity_id, surface)
                aliases_by_node[surface.entity_id].add(surface.surface_form)
                surfaces_by_exchange[turn.exchange_id].setdefault(surface.entity_id, surface)
                evidence_by_node[surface.entity_id].append(GraphEvidenceRef(
                    exchange_id=turn.exchange_id,
                    turn_ids=(turn.turn_id,),
                    policy_ids=(turn.source_policy_id,),
                    observed_at_utc=turn.created_at_utc,
                    suppressed=False,
                ))

        nodes = {}
        for node_id, surface in surface_by_node.items():
            refs = tuple(sorted(
                set(evidence_by_node[node_id]),
                key=lambda ref: (
                    ref.exchange_id,
                    ref.turn_ids,
                    tuple(policy or '' for policy in ref.policy_ids),
                ),
            ))
            nodes[node_id] = GraphNode(
                node_id=node_id,
                canonical_label=surface.canonical_label,
                entity_type=surface.entity_type,
                aliases=tuple(sorted(aliases_by_node[node_id])),
                source_refs=refs,
                first_seen_utc=min(ref.observed_at_utc for ref in refs),
                last_seen_utc=max(ref.observed_at_utc for ref in refs),
                observation_count=len({ref.exchange_id for ref in refs}),
            )

        edge_exchanges: dict[tuple[str, str], list[str]] = defaultdict(list)
        exchange_times = {}
        for turn in snapshot.turns:
            exchange_times.setdefault(turn.exchange_id, turn.created_at_utc)
        for exchange_id, surfaces in surfaces_by_exchange.items():
            for left_id, right_id in combinations(sorted(surfaces), 2):
                edge_exchanges[(left_id, right_id)].append(exchange_id)
        edges = {}
        for node_pair, exchange_ids in edge_exchanges.items():
            source_id, target_id = node_pair
            digest = hashlib.sha256(
                f'co_occurs\x00{source_id}\x00{target_id}'.encode('ascii')
            ).hexdigest()[:24]
            edge_id = f'edge-{digest}'
            source_ids = tuple(sorted(set(exchange_ids)))
            timestamps = [exchange_times[item] for item in source_ids]
            edges[edge_id] = GraphEdge(
                edge_id=edge_id,
                source_node_id=source_id,
                target_node_id=target_id,
                relation='co_occurs',
                weight=len(source_ids),
                source_exchange_ids=source_ids,
                first_seen_utc=min(timestamps),
                last_seen_utc=max(timestamps),
            )

        exclusions = []
        for node_id, node in historical_state.nodes.items():
            if node_id in nodes:
                continue
            matching_turns = [
                effective_turn_by_id[turn_id]
                for source in node.source_refs
                for turn_id in source.turn_ids
                if turn_id in effective_turn_by_id
            ]
            policy_ids = tuple(sorted({
                turn.source_policy_id
                for turn in matching_turns
                if turn.source_policy_id is not None
            }))
            if any(turn.forgotten for turn in matching_turns):
                reason = 'FORGOTTEN_SOURCE'
            elif policy_ids:
                reason = 'SUPERSEDED_SOURCE'
            else:
                reason = 'NO_EFFECTIVE_SOURCE'
            exclusions.append(PolicyExclusion(node_id, reason, policy_ids))

        timestamps = [turn.created_at_utc for turn in snapshot.turns]
        effective_state = GraphState(
            extractor_version=ExplicitEntityExtractor.version,
            processed_exchange_ids=tuple(sorted(surfaces_by_exchange)),
            nodes=dict(sorted(nodes.items())),
            edges=dict(sorted(edges.items())),
            updated_at_utc=(
                max(timestamps) if timestamps else historical_state.updated_at_utc
            ),
        )
        return EffectiveGraphView(
            state=effective_state,
            exclusions=tuple(sorted(exclusions, key=lambda item: item.node_id)),
            policy_revision=snapshot.policy_revision,
        )


@dataclass(frozen=True)
class PPRNodeScore:
    node_id: str
    score: float


@dataclass(frozen=True)
class PPRResult:
    seed_node_ids: tuple[str, ...]
    scores: tuple[PPRNodeScore, ...]
    associative_scores: tuple[PPRNodeScore, ...]
    damping_factor: float
    tolerance: float
    max_iterations: int
    iterations: int
    converged: bool


class PersonalizedPageRank:
    def __init__(
        self,
        *,
        damping_factor: float = PPR_DAMPING_FACTOR,
        tolerance: float = PPR_TOLERANCE,
        max_iterations: int = PPR_MAX_ITERATIONS,
    ):
        if not 0 < damping_factor < 1:
            raise ValueError('damping factor must be between zero and one')
        if tolerance <= 0:
            raise ValueError('convergence tolerance must be positive')
        if max_iterations <= 0:
            raise ValueError('maximum iterations must be positive')
        self.damping_factor = damping_factor
        self.tolerance = tolerance
        self.max_iterations = max_iterations

    def rank(
        self,
        state: GraphState | None,
        seed_node_ids: tuple[str, ...],
    ) -> PPRResult:
        seeds = tuple(sorted(set(seed_node_ids)))
        if state is None or not seeds or any(seed not in state.nodes for seed in seeds):
            return self._result(seeds, (), 0, True)

        node_ids = tuple(sorted(state.nodes))
        adjacency = {node_id: {} for node_id in node_ids}
        for edge in state.edges.values():
            adjacency[edge.source_node_id][edge.target_node_id] = edge.weight
            adjacency[edge.target_node_id][edge.source_node_id] = edge.weight
        totals = {
            node_id: sum(neighbors.values())
            for node_id, neighbors in adjacency.items()
        }
        personalization = {
            node_id: (1.0 / len(seeds) if node_id in seeds else 0.0)
            for node_id in node_ids
        }
        scores = dict(personalization)
        for iteration in range(1, self.max_iterations + 1):
            previous_scores = dict(scores)
            dangling_mass = sum(
                scores[node_id]
                for node_id in node_ids
                if totals[node_id] == 0
            )
            for node_id in node_ids:
                incoming = sum(
                    scores[source_id] * adjacency[source_id][node_id] / totals[source_id]
                    for source_id in adjacency[node_id]
                    if totals[source_id] > 0
                )
                scores[node_id] = (
                    (1.0 - self.damping_factor) * personalization[node_id]
                    + self.damping_factor * dangling_mass * personalization[node_id]
                    + self.damping_factor * incoming
                )
            delta = sum(
                abs(scores[node_id] - previous_scores[node_id])
                for node_id in node_ids
            )
            if delta <= self.tolerance:
                ranked = tuple(sorted(
                    (
                        PPRNodeScore(node_id, float(format(score, '.15g')))
                        for node_id, score in scores.items()
                        if score > 0
                    ),
                    key=cmp_to_key(self._compare_scores),
                ))
                return self._result(seeds, ranked, iteration, True)
        return self._result(seeds, (), self.max_iterations, False)

    def _compare_scores(self, left: PPRNodeScore, right: PPRNodeScore) -> int:
        if abs(left.score - right.score) <= self.tolerance:
            return (left.node_id > right.node_id) - (left.node_id < right.node_id)
        return -1 if left.score > right.score else 1

    def _result(
        self,
        seeds: tuple[str, ...],
        scores: tuple[PPRNodeScore, ...],
        iterations: int,
        converged: bool,
    ) -> PPRResult:
        return PPRResult(
            seed_node_ids=seeds,
            scores=scores,
            associative_scores=tuple(
                score for score in scores if score.node_id not in seeds
            ),
            damping_factor=self.damping_factor,
            tolerance=self.tolerance,
            max_iterations=self.max_iterations,
            iterations=iterations,
            converged=converged,
        )


class ShadowReceiptStore:
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = os.fspath(directory)

    def save(self, receipt: dict) -> None:
        directory = os.path.abspath(self.directory)
        path = os.path.join(directory, f"{receipt['receipt_id']}.json")
        temporary = f'{path}.tmp'
        try:
            os.makedirs(directory, exist_ok=True)
            with open(temporary, 'w', encoding='utf-8') as stream:
                json.dump(receipt, stream, ensure_ascii=True, indent=2, sort_keys=True)
                stream.write('\n')
            os.replace(temporary, path)
        except OSError as exc:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise GraphMemoryError('could not save graph retrieval receipt') from exc

    def why(self, receipt_id: str) -> dict:
        path = os.path.join(os.path.abspath(self.directory), f'{receipt_id}.json')
        try:
            with open(path, encoding='utf-8') as stream:
                receipt = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise GraphMemoryError(f'graph retrieval receipt not found: {receipt_id}') from exc
        if receipt.get('receipt_id') != receipt_id:
            raise GraphMemoryError('graph retrieval receipt is malformed')
        return receipt


class GraphShadowRetriever:
    def __init__(
        self,
        receipt_store: ShadowReceiptStore | None = None,
        *,
        query_extractor: GraphQueryExtractor | None = None,
        graph_builder: EffectiveGraphBuilder | None = None,
        ranker: PersonalizedPageRank | None = None,
        candidate_limit: int = 3,
    ):
        if candidate_limit <= 0:
            raise ValueError('candidate limit must be positive')
        self.receipt_store = receipt_store
        self.query_extractor = query_extractor or GraphQueryExtractor()
        self.graph_builder = graph_builder or EffectiveGraphBuilder()
        self.ranker = ranker or PersonalizedPageRank()
        self.candidate_limit = candidate_limit

    def retrieve(
        self,
        *,
        query_turn_id: str,
        content: str,
        historical_state: GraphState,
        effective_snapshot: EffectiveMemorySnapshot,
    ) -> dict:
        started = time.perf_counter()
        view = self.graph_builder.build(historical_state, effective_snapshot)
        extraction = self.query_extractor.extract(
            query_turn_id=query_turn_id,
            content=content,
            state=view.state,
        )
        exclusions_by_id = {
            exclusion.node_id: exclusion
            for exclusion in view.exclusions
        }
        eligible_seeds = tuple(
            node_id
            for node_id in extraction.seed_entity_ids
            if node_id in view.state.nodes
        )
        ppr = self.ranker.rank(view.state, eligible_seeds)
        rejected = []
        for entity in extraction.entities:
            exclusion = exclusions_by_id.get(entity.entity_id)
            if exclusion is not None:
                rejected.append({
                    'node_id': entity.entity_id,
                    'policy_ids': list(exclusion.policy_ids),
                    'reason': exclusion.reason,
                })
        raw_candidates = [
            {'node_id': item.node_id, 'score': item.score}
            for item in ppr.scores
        ]
        filtered = []
        for item in ppr.scores:
            if item.node_id in eligible_seeds:
                rejected.append({
                    'node_id': item.node_id,
                    'policy_ids': [],
                    'reason': 'QUERY_SEED',
                })
                continue
            if len(filtered) >= self.candidate_limit:
                rejected.append({
                    'node_id': item.node_id,
                    'policy_ids': [],
                    'reason': 'RANK_LIMIT',
                })
                continue
            node = view.state.nodes[item.node_id]
            filtered.append({
                'node_id': node.node_id,
                'canonical_label': node.canonical_label,
                'entity_type': node.entity_type,
                'aliases': list(node.aliases),
                'score': item.score,
                'source_refs': [
                    {
                        **asdict(source),
                        'turn_ids': list(source.turn_ids),
                        'policy_ids': list(source.policy_ids),
                    }
                    for source in node.source_refs
                ],
                'historical_status': 'effective',
            })
        if not ppr.converged:
            rejected.append({
                'node_id': None,
                'policy_ids': [],
                'reason': 'PPR_NON_CONVERGENCE',
            })

        snapshot_payload = json.dumps(
            asdict(view.state),
            ensure_ascii=True,
            separators=(',', ':'),
            sort_keys=True,
        ).encode('utf-8')
        graph_snapshot_id = hashlib.sha256(snapshot_payload).hexdigest()
        receipt_id = 'retrieval-' + hashlib.sha256(
            f'{query_turn_id}\x00{graph_snapshot_id}'.encode('utf-8')
        ).hexdigest()[:24]
        receipt = {
            'schema_version': 1,
            'receipt_id': receipt_id,
            'query_turn_id': query_turn_id,
            'query_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(),
            'extractor_version': extraction.extractor_version,
            'raw_seed_entities': [asdict(entity) for entity in extraction.entities],
            'seed_entity_ids': list(eligible_seeds),
            'unresolved_surface_forms': list(extraction.unresolved_surface_forms),
            'graph_snapshot_id': graph_snapshot_id,
            'policy_revision': view.policy_revision,
            'ppr': {
                'damping_factor': ppr.damping_factor,
                'tolerance': ppr.tolerance,
                'max_iterations': ppr.max_iterations,
                'iterations': ppr.iterations,
                'converged': ppr.converged,
            },
            'raw_ppr_candidates': raw_candidates,
            'filtered_candidates': filtered,
            'rejected_candidates': rejected,
            'latency_seconds': time.perf_counter() - started,
            'retrieval_count': 1,
            'retrieval_injection_count': 0,
            'retrieval_influence_count': 0,
        }
        if self.receipt_store is not None:
            self.receipt_store.save(receipt)
        return receipt

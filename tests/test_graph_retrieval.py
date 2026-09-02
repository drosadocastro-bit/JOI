from copy import deepcopy

import pytest

from memory.graph_memory import (
    build_entity_id,
    ExplicitEntityExtractor,
    GraphMemoryManager,
    GraphMemoryStore,
)
from memory.graph_retrieval import (
    PPR_DAMPING_FACTOR,
    PPR_MAX_ITERATIONS,
    PPR_TOLERANCE,
    EffectiveGraphBuilder,
    GraphQueryExtractor,
    GraphShadowRetriever,
    PersonalizedPageRank,
    ShadowReceiptStore,
)
from memory.memory_store import (
    EffectiveMemorySnapshot,
    EffectiveMemoryTurn,
    EpisodicTurn,
)


def _exchange(exchange_id: str, user: str, timestamp: str):
    return (
        EpisodicTurn(
            turn_id=f'{exchange_id}-user',
            exchange_id=exchange_id,
            role='user',
            content=user,
            created_at_utc=timestamp,
            schema_version=1,
        ),
        EpisodicTurn(
            turn_id=f'{exchange_id}-assistant',
            exchange_id=exchange_id,
            role='assistant',
            content='Noted.',
            created_at_utc=timestamp,
            schema_version=1,
        ),
    )


def _state(tmp_path):
    manager = GraphMemoryManager(
        GraphMemoryStore(tmp_path / 'graph.json'),
        ExplicitEntityExtractor(),
    )
    manager.update(_exchange(
        'source-1',
        'My name is Jose. I am working on Project Atlas. '
        'We are discussing source provenance. I live in Lisbon. '
        'I prefer cafe. Remember that release is Friday. '
        'The current task is memory audit.',
        '2026-09-02T09:00:00+00:00',
    ))
    return manager.state


@pytest.mark.parametrize(
    ('query', 'entity_type', 'canonical_label', 'surface_form'),
    [
        ('My name is Jose.', 'person', 'jose', 'Jose'),
        ('I am working on Project Atlas.', 'project', 'project atlas', 'Project Atlas'),
        ('We are discussing source provenance.', 'concept', 'source provenance', 'source provenance'),
        ('I live in Lisbon.', 'place', 'lisbon', 'Lisbon'),
        ('I prefer cafe.', 'preference', 'cafe', 'cafe'),
        ('Remember that release is Friday.', 'fact', 'release is friday', 'release is Friday'),
        ('The current task is memory audit.', 'task_topic', 'memory audit', 'memory audit'),
    ],
)
def test_query_extractor_resolves_exact_supported_surfaces(
    tmp_path,
    query,
    entity_type,
    canonical_label,
    surface_form,
):
    result = GraphQueryExtractor().extract(
        query_turn_id='query-1-user',
        content=query,
        state=_state(tmp_path),
    )

    assert len(result.entities) == 1
    entity = result.entities[0]
    assert entity.entity_type == entity_type
    assert entity.canonical_label == canonical_label
    assert entity.surface_form == surface_form
    assert result.seed_entity_ids == (entity.entity_id,)
    assert result.unresolved_surface_forms == ()
    assert result.extractor_version == 'explicit-patterns-v1'


def test_query_extractor_keeps_unknown_explicit_surface_unresolved(tmp_path):
    result = GraphQueryExtractor().extract(
        query_turn_id='query-unknown-user',
        content='I am working on Project Orion.',
        state=_state(tmp_path),
    )

    assert result.seed_entity_ids == ()
    assert result.unresolved_surface_forms == ('Project Orion',)
    assert result.entities[0].canonical_label == 'project orion'


def test_query_extractor_does_not_infer_unsupported_bilingual_surface(tmp_path):
    result = GraphQueryExtractor().extract(
        query_turn_id='query-es-user',
        content='Mi nombre es Jose.',
        state=_state(tmp_path),
    )

    assert result.entities == ()
    assert result.seed_entity_ids == ()
    assert result.unresolved_surface_forms == ()


def test_query_extractor_collapses_duplicate_aliases(tmp_path):
    result = GraphQueryExtractor().extract(
        query_turn_id='query-duplicate-user',
        content='I prefer cafe. I prefer cafe.',
        state=_state(tmp_path),
    )

    assert len(result.entities) == 1
    assert len(result.seed_entity_ids) == 1
    assert result.unresolved_surface_forms == ()


def test_query_extractor_allows_zero_seeds_without_graph(tmp_path):
    result = GraphQueryExtractor().extract(
        query_turn_id='query-empty-user',
        content='Nothing explicit here.',
        state=None,
    )

    assert result.entities == ()
    assert result.seed_entity_ids == ()
    assert result.unresolved_surface_forms == ()


def test_query_extractor_does_not_mutate_graph(tmp_path):
    state = _state(tmp_path)
    before = deepcopy(state)

    GraphQueryExtractor().extract(
        query_turn_id='query-read-only-user',
        content='My name is Jose. I am working on Project Orion.',
        state=state,
    )

    assert state == before


def test_query_extractor_matches_phase_5b_explicit_semantics(tmp_path):
    content = (
        'My name is Jose. I am working on Project Atlas. '
        'We are discussing source provenance. I live in Lisbon. '
        'I prefer cafe. Remember that release is Friday. '
        'The current task is memory audit.'
    )
    turns = _exchange(
        'contract-source',
        content,
        '2026-09-02T09:30:00+00:00',
    )

    write_entities = ExplicitEntityExtractor().extract(turns)
    query_entities = GraphQueryExtractor().extract(
        query_turn_id='contract-query-user',
        content=content,
        state=None,
    ).entities

    assert [
        (item.entity_id, item.entity_type, item.canonical_label, item.surface_form)
        for item in query_entities
    ] == [
        (item.entity_id, item.entity_type, item.canonical_label, item.surface_form)
        for item in write_entities
    ]


def _association_state(tmp_path):
    manager = GraphMemoryManager(
        GraphMemoryStore(tmp_path / 'associations.json'),
        ExplicitEntityExtractor(),
    )
    manager.update(_exchange(
        'association-1',
        'We are discussing AI. I am working on Project Helios.',
        '2026-09-02T10:00:00+00:00',
    ))
    manager.update(_exchange(
        'association-2',
        'We are discussing AI. I am working on Project Borealis.',
        '2026-09-02T10:01:00+00:00',
    ))
    manager.update(_exchange(
        'association-3',
        'I prefer tea.',
        '2026-09-02T10:02:00+00:00',
    ))
    return manager.state


def test_ppr_uses_frozen_parameters_and_is_deterministic(tmp_path):
    state = _association_state(tmp_path)
    seed = next(
        node.node_id
        for node in state.nodes.values()
        if node.canonical_label == 'ai'
    )
    ranker = PersonalizedPageRank()

    first = ranker.rank(state, (seed,))
    second = ranker.rank(state, (seed,))

    assert PPR_DAMPING_FACTOR == 0.85
    assert PPR_TOLERANCE == 1e-12
    assert PPR_MAX_ITERATIONS == 100
    assert first == second
    assert first.converged is True
    assert 0 < first.iterations <= PPR_MAX_ITERATIONS
    assert first.damping_factor == PPR_DAMPING_FACTOR
    assert first.tolerance == PPR_TOLERANCE


def test_ppr_breaks_equal_score_ties_by_node_id(tmp_path):
    state = _association_state(tmp_path)
    seed = next(
        node.node_id
        for node in state.nodes.values()
        if node.canonical_label == 'ai'
    )

    result = PersonalizedPageRank().rank(state, (seed,))
    project_scores = [
        score
        for score in result.scores
        if state.nodes[score.node_id].entity_type == 'project'
    ]

    assert len(project_scores) == 2
    assert abs(project_scores[0].score - project_scores[1].score) <= PPR_TOLERANCE
    assert [item.node_id for item in project_scores] == sorted(
        item.node_id for item in project_scores
    )


def test_ppr_empty_and_disconnected_graphs_return_no_associations(tmp_path):
    state = _association_state(tmp_path)
    isolated_seed = next(
        node.node_id
        for node in state.nodes.values()
        if node.canonical_label == 'tea'
    )

    assert PersonalizedPageRank().rank(None, ()).scores == ()
    disconnected = PersonalizedPageRank().rank(state, (isolated_seed,))
    assert disconnected.converged is True
    assert disconnected.associative_scores == ()


def test_ppr_non_convergence_exposes_no_scores(tmp_path):
    state = _association_state(tmp_path)
    seed = next(
        node.node_id
        for node in state.nodes.values()
        if node.canonical_label == 'ai'
    )

    result = PersonalizedPageRank(max_iterations=1).rank(state, (seed,))

    assert result.converged is False
    assert result.scores == ()
    assert result.associative_scores == ()


def test_ppr_does_not_mutate_graph_or_open_network(monkeypatch, tmp_path):
    state = _association_state(tmp_path)
    before = deepcopy(state)
    seed = next(iter(state.nodes))

    monkeypatch.setattr(
        'socket.socket',
        lambda *args, **kwargs: pytest.fail('network path opened'),
    )
    PersonalizedPageRank().rank(state, (seed,))

    assert state == before


def _policy_state_and_snapshot(tmp_path):
    manager = GraphMemoryManager(
        GraphMemoryStore(tmp_path / 'policy-graph.json'),
        ExplicitEntityExtractor(),
    )
    manager.update(_exchange(
        'policy-source-1',
        'My name is Luna. I prefer green tea.',
        '2026-09-02T11:00:00+00:00',
    ))
    manager.update(_exchange(
        'policy-source-2',
        'I am working on Project Atlas. I live in Madrid.',
        '2026-09-02T11:01:00+00:00',
    ))
    snapshot = EffectiveMemorySnapshot(
        policy_revision=2,
        turns=(
            EffectiveMemoryTurn(
                turn_id='policy-source-1-user',
                exchange_id='policy-source-1',
                role='user',
                content=None,
                source_policy_id='policy-forget-1',
                forgotten=True,
                completed_exchange=True,
                created_at_utc='2026-09-02T11:00:00+00:00',
            ),
            EffectiveMemoryTurn(
                turn_id='policy-source-1-assistant',
                exchange_id='policy-source-1',
                role='assistant',
                content='Noted.',
                source_policy_id=None,
                forgotten=False,
                completed_exchange=True,
                created_at_utc='2026-09-02T11:00:00+00:00',
            ),
            EffectiveMemoryTurn(
                turn_id='policy-source-2-user',
                exchange_id='policy-source-2',
                role='user',
                content='I am working on Project Atlas. I live in Lisbon.',
                source_policy_id='policy-correct-2',
                forgotten=False,
                completed_exchange=True,
                created_at_utc='2026-09-02T11:01:00+00:00',
            ),
            EffectiveMemoryTurn(
                turn_id='policy-source-2-assistant',
                exchange_id='policy-source-2',
                role='assistant',
                content='Noted.',
                source_policy_id=None,
                forgotten=False,
                completed_exchange=True,
                created_at_utc='2026-09-02T11:01:00+00:00',
            ),
        ),
    )
    return manager.state, snapshot


def test_effective_graph_marks_forgotten_entities_forbidden(tmp_path):
    historical, snapshot = _policy_state_and_snapshot(tmp_path)

    view = EffectiveGraphBuilder().build(historical, snapshot)

    assert view.exclusion_for(build_entity_id('person', 'luna')).reason == 'FORGOTTEN_SOURCE'
    assert view.exclusion_for(build_entity_id('preference', 'green tea')).reason == 'FORGOTTEN_SOURCE'
    assert build_entity_id('person', 'luna') not in view.state.nodes


def test_effective_graph_marks_superseded_entity_stale(tmp_path):
    historical, snapshot = _policy_state_and_snapshot(tmp_path)

    view = EffectiveGraphBuilder().build(historical, snapshot)

    exclusion = view.exclusion_for(build_entity_id('place', 'madrid'))
    assert exclusion.reason == 'SUPERSEDED_SOURCE'
    assert exclusion.policy_ids == ('policy-correct-2',)


def test_effective_graph_makes_corrected_replacement_eligible(tmp_path):
    historical, snapshot = _policy_state_and_snapshot(tmp_path)

    view = EffectiveGraphBuilder().build(historical, snapshot)
    lisbon = view.state.nodes[build_entity_id('place', 'lisbon')]

    assert lisbon.canonical_label == 'lisbon'
    assert lisbon.source_refs[0].policy_ids == ('policy-correct-2',)
    assert lisbon.source_refs[0].suppressed is False


def test_effective_graph_preserves_entity_present_after_correction(tmp_path):
    historical, snapshot = _policy_state_and_snapshot(tmp_path)
    historical_before = deepcopy(historical)
    snapshot_before = deepcopy(snapshot)

    view = EffectiveGraphBuilder().build(historical, snapshot)
    atlas_id = build_entity_id('project', 'project atlas')
    lisbon_id = build_entity_id('place', 'lisbon')

    assert atlas_id in view.state.nodes
    assert any(
        {edge.source_node_id, edge.target_node_id} == {atlas_id, lisbon_id}
        for edge in view.state.edges.values()
    )
    assert historical == historical_before
    assert snapshot == snapshot_before


def _receipt_state(tmp_path):
    manager = GraphMemoryManager(
        GraphMemoryStore(tmp_path / 'receipt-graph.json'),
        ExplicitEntityExtractor(),
    )
    manager.update(_exchange(
        'receipt-source-1',
        'My name is Jose. I prefer cafe.',
        '2026-09-02T09:00:00+00:00',
    ))
    return manager.state


def _active_snapshot():
    return EffectiveMemorySnapshot(
        policy_revision=0,
        turns=(
            EffectiveMemoryTurn(
                turn_id='receipt-source-1-user',
                exchange_id='receipt-source-1',
                role='user',
                content=(
                    'My name is Jose. I prefer cafe.'
                ),
                source_policy_id=None,
                forgotten=False,
                completed_exchange=True,
                created_at_utc='2026-09-02T09:00:00+00:00',
            ),
            EffectiveMemoryTurn(
                turn_id='receipt-source-1-assistant',
                exchange_id='receipt-source-1',
                role='assistant',
                content='Noted.',
                source_policy_id=None,
                forgotten=False,
                completed_exchange=True,
                created_at_utc='2026-09-02T09:00:00+00:00',
            ),
        ),
    )


def test_shadow_receipt_records_raw_filtered_and_rejected_candidates(tmp_path):
    historical = _receipt_state(tmp_path)
    store = ShadowReceiptStore(tmp_path / 'receipts')
    retriever = GraphShadowRetriever(store)

    receipt = retriever.retrieve(
        query_turn_id='query-jose-user',
        content='My name is Jose.',
        historical_state=historical,
        effective_snapshot=_active_snapshot(),
    )

    jose_id = build_entity_id('person', 'jose')
    cafe_id = build_entity_id('preference', 'cafe')
    assert receipt['seed_entity_ids'] == [jose_id]
    assert receipt['unresolved_surface_forms'] == []
    assert receipt['raw_seed_entities'][0]['surface_form'] == 'Jose'
    assert any(item['node_id'] == jose_id for item in receipt['raw_ppr_candidates'])
    assert any(item['node_id'] == cafe_id for item in receipt['filtered_candidates'])
    assert any(
        item['node_id'] == jose_id and item['reason'] == 'QUERY_SEED'
        for item in receipt['rejected_candidates']
    )
    cafe = next(
        item for item in receipt['filtered_candidates']
        if item['node_id'] == cafe_id
    )
    assert cafe['source_refs'][0]['turn_ids'] == ['receipt-source-1-user']
    assert cafe['source_refs'][0]['policy_ids'] == [None]
    assert cafe['score'] > 0
    assert receipt['latency_seconds'] >= 0
    assert receipt['retrieval_count'] == 1
    assert receipt['retrieval_injection_count'] == 0
    assert receipt['retrieval_influence_count'] == 0
    assert 'prompt' not in receipt
    assert store.why(receipt['receipt_id']) == receipt


@pytest.mark.parametrize(
    ('query', 'entity_type', 'label', 'reason'),
    [
        ('My name is Luna.', 'person', 'luna', 'FORGOTTEN_SOURCE'),
        ('I live in Madrid.', 'place', 'madrid', 'SUPERSEDED_SOURCE'),
    ],
)
def test_shadow_receipt_rejects_policy_ineligible_seed(
    tmp_path,
    query,
    entity_type,
    label,
    reason,
):
    historical, snapshot = _policy_state_and_snapshot(tmp_path)

    receipt = GraphShadowRetriever().retrieve(
        query_turn_id='query-policy-user',
        content=query,
        historical_state=historical,
        effective_snapshot=snapshot,
    )

    node_id = build_entity_id(entity_type, label)
    assert receipt['seed_entity_ids'] == []
    assert receipt['filtered_candidates'] == []
    assert receipt['rejected_candidates'] == [{
        'node_id': node_id,
        'policy_ids': receipt['rejected_candidates'][0]['policy_ids'],
        'reason': reason,
    }]
    assert receipt['ppr']['converged'] is True


def test_shadow_retrieval_accepts_corrected_replacement_seed(tmp_path):
    historical, snapshot = _policy_state_and_snapshot(tmp_path)

    receipt = GraphShadowRetriever().retrieve(
        query_turn_id='query-lisbon-user',
        content='I live in Lisbon.',
        historical_state=historical,
        effective_snapshot=snapshot,
    )

    assert receipt['seed_entity_ids'] == [build_entity_id('place', 'lisbon')]
    assert any(
        item['node_id'] == build_entity_id('project', 'project atlas')
        for item in receipt['filtered_candidates']
    )


def test_shadow_retrieval_preserves_entity_across_correction(tmp_path):
    historical, snapshot = _policy_state_and_snapshot(tmp_path)

    receipt = GraphShadowRetriever().retrieve(
        query_turn_id='query-atlas-user',
        content='I am working on Project Atlas.',
        historical_state=historical,
        effective_snapshot=snapshot,
    )

    assert receipt['seed_entity_ids'] == [
        build_entity_id('project', 'project atlas')
    ]
    assert any(
        item['node_id'] == build_entity_id('place', 'lisbon')
        for item in receipt['filtered_candidates']
    )


def test_shadow_retrieval_does_not_mutate_sources(tmp_path):
    historical = _receipt_state(tmp_path)
    snapshot = _active_snapshot()
    historical_before = deepcopy(historical)
    snapshot_before = deepcopy(snapshot)

    GraphShadowRetriever().retrieve(
        query_turn_id='query-read-only-user',
        content='My name is Jose.',
        historical_state=historical,
        effective_snapshot=snapshot,
    )

    assert historical == historical_before
    assert snapshot == snapshot_before

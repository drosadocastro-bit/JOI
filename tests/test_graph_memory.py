import json
import os
from dataclasses import replace
from unittest.mock import Mock

import pytest

from memory.graph_memory import (
    EntityCandidate,
    ExplicitEntityExtractor,
    GraphEvidenceRef,
    GraphMemoryError,
    GraphMemoryManager,
    GraphMemoryStore,
    GraphMemoryWorker,
    build_entity_id,
)
from memory.memory_store import EpisodicTurn, MemoryPolicyRecord


def _turn(turn_id, role, content):
    return EpisodicTurn(
        turn_id=turn_id,
        exchange_id='exchange-1',
        role=role,
        content=content,
        created_at_utc='2026-09-01T12:00:00+00:00',
        schema_version=1,
    )


def _exchange():
    return (
        _turn('turn-user', 'user', 'My name is Luna. I prefer green tea.'),
        _turn('turn-assistant', 'assistant', 'I understand.'),
    )


def test_explicit_extractor_emits_only_source_linked_surface_forms():
    candidates = ExplicitEntityExtractor().extract(_exchange())

    assert [(item.entity_type, item.canonical_label) for item in candidates] == [
        ('person', 'luna'),
        ('preference', 'green tea'),
    ]
    assert all(item.status == 'explicit' for item in candidates)
    assert all(item.surface_form in _exchange()[0].content for item in candidates)
    assert all(item.evidence.exchange_id == 'exchange-1' for item in candidates)
    assert all(item.evidence.turn_ids == ('turn-user',) for item in candidates)
    assert all(item.evidence.policy_ids == (None,) for item in candidates)


def test_explicit_extractor_does_not_infer_hidden_state_or_sparse_entities():
    turns = (
        _turn('turn-user', 'user', 'I am exhausted and perhaps sad.'),
        _turn('turn-assistant', 'assistant', 'That sounds difficult.'),
    )

    assert ExplicitEntityExtractor().extract(turns) == ()


def test_manager_writes_nodes_edge_and_replay_is_idempotent(tmp_path):
    path = tmp_path / 'graph.json'
    manager = GraphMemoryManager(GraphMemoryStore(path), ExplicitEntityExtractor())

    first = manager.update(_exchange())
    first_bytes = path.read_bytes()
    replay = manager.update(_exchange())

    assert replay == first
    assert path.read_bytes() == first_bytes
    assert first.processed_exchange_ids == ('exchange-1',)
    assert len(first.nodes) == 2
    assert len(first.edges) == 1
    edge = next(iter(first.edges.values()))
    assert edge.relation == 'co_occurs'
    assert edge.weight == 1
    assert edge.source_exchange_ids == ('exchange-1',)
    assert all(node.observation_count == 1 for node in first.nodes.values())


def test_fresh_replay_is_byte_deterministic(tmp_path):
    first_path = tmp_path / 'first.json'
    second_path = tmp_path / 'second.json'

    GraphMemoryManager(
        GraphMemoryStore(first_path), ExplicitEntityExtractor()
    ).update(_exchange())
    GraphMemoryManager(
        GraphMemoryStore(second_path), ExplicitEntityExtractor()
    ).update(_exchange())

    assert first_path.read_bytes() == second_path.read_bytes()


def test_manager_rejects_unsupported_candidate_without_partial_write(tmp_path):
    class UnsupportedExtractor:
        version = 'malformed-v1'

        def extract(self, turns):
            evidence = GraphEvidenceRef(
                exchange_id='exchange-1',
                turn_ids=('turn-user',),
                policy_ids=(None,),
                observed_at_utc='2026-09-01T12:00:00+00:00',
                suppressed=False,
            )
            return (EntityCandidate(
                entity_id=build_entity_id('person', 'invented'),
                canonical_label='invented',
                surface_form='invented',
                entity_type='person',
                evidence=evidence,
                extractor_version=self.version,
                status='explicit',
            ),)

    path = tmp_path / 'graph.json'
    manager = GraphMemoryManager(GraphMemoryStore(path), UnsupportedExtractor())

    with pytest.raises(GraphMemoryError, match='unsupported surface form'):
        manager.update(_exchange())

    assert not path.exists()


def test_policy_update_suppresses_matching_source_without_erasing_lineage(tmp_path):
    path = tmp_path / 'graph.json'
    manager = GraphMemoryManager(GraphMemoryStore(path), ExplicitEntityExtractor())
    state = manager.update(_exchange())
    person_id = build_entity_id('person', 'luna')
    policy = MemoryPolicyRecord(
        policy_id='policy-1',
        target_turn_id='turn-user',
        action='forget',
        replacement_content=None,
        reason='user request',
        supersedes_policy_id=None,
        created_at_utc='2026-09-01T12:30:00+00:00',
        schema_version=1,
    )

    updated = manager.apply_policy(policy)
    source = updated.nodes[person_id].source_refs[0]

    assert source.exchange_id == state.nodes[person_id].source_refs[0].exchange_id
    assert source.policy_ids == ('policy-1',)
    assert source.suppressed is True
    assert path.exists()


@pytest.mark.parametrize('payload', [
    '{broken',
    json.dumps({'schema_version': 99}),
])
def test_store_rejects_corrupt_or_unknown_schema_without_repair(tmp_path, payload):
    path = tmp_path / 'graph.json'
    path.write_text(payload, encoding='utf-8')
    original = path.read_bytes()

    with pytest.raises(GraphMemoryError):
        GraphMemoryStore(path).load()

    assert path.read_bytes() == original


def test_candidate_identity_is_type_scoped():
    assert build_entity_id('person', 'Luna') != build_entity_id('project', 'Luna')
    assert build_entity_id('person', 'Luna') == build_entity_id('person', ' luna ')


def test_manager_inspection_is_bounded_and_source_linked(tmp_path):
    manager = GraphMemoryManager(
        GraphMemoryStore(tmp_path / 'graph.json'),
        ExplicitEntityExtractor(),
    )
    state = manager.update(_exchange())
    person_id = build_entity_id('person', 'luna')
    edge_id = next(iter(state.edges))

    assert manager.status() == {
        'schema_version': 1,
        'extractor_version': 'explicit-patterns-v1',
        'processed_exchange_count': 1,
        'node_count': 2,
        'edge_count': 1,
        'suppressed_source_count': 0,
    }
    assert person_id in {node.node_id for node in manager.recent(2)}
    assert manager.why(person_id) == state.nodes[person_id]
    assert manager.why(edge_id) == state.edges[edge_id]
    with pytest.raises(GraphMemoryError, match='graph item not found'):
        manager.why('missing')


def test_worker_contains_update_failure_and_logs_content_free_metadata():
    manager = Mock()
    manager.update.side_effect = RuntimeError('write failed')
    logger = Mock()
    worker = GraphMemoryWorker(manager, logger)

    worker.submit(_exchange())
    worker.wait_for_idle()
    worker.close()

    logger.exception.assert_called_once_with('Graph memory update failed')
    assert 'green tea' not in repr(logger.method_calls)


def test_worker_serializes_policy_after_exchange():
    manager = Mock()
    manager.update.return_value = Mock(nodes={}, edges={}, processed_exchange_ids=())
    manager.apply_policy.return_value = Mock(nodes={})
    logger = Mock()
    worker = GraphMemoryWorker(manager, logger)
    policy = MemoryPolicyRecord(
        policy_id='policy-1',
        target_turn_id='turn-user',
        action='correct',
        replacement_content='Corrected',
        reason='user request',
        supersedes_policy_id=None,
        created_at_utc='2026-09-01T12:30:00+00:00',
        schema_version=1,
    )

    worker.submit(_exchange())
    worker.submit_policy(policy)
    worker.wait_for_idle()
    worker.close()

    manager.update.assert_called_once_with(_exchange())
    manager.apply_policy.assert_called_once_with(policy)


def test_store_rejects_edge_without_endpoint_evidence(tmp_path):
    path = tmp_path / 'graph.json'
    manager = GraphMemoryManager(GraphMemoryStore(path), ExplicitEntityExtractor())
    manager.update(_exchange())
    payload = json.loads(path.read_text(encoding='utf-8'))
    edge = next(iter(payload['edges'].values()))
    edge['source_exchange_ids'] = ['unsupported-exchange']
    path.write_text(json.dumps(payload), encoding='utf-8')

    with pytest.raises(GraphMemoryError, match='graph edge is malformed'):
        GraphMemoryStore(path).load()


def test_failed_atomic_save_preserves_previous_bytes_and_manager_state(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / 'graph.json'
    manager = GraphMemoryManager(GraphMemoryStore(path), ExplicitEntityExtractor())
    previous_state = manager.update(_exchange())
    previous_bytes = path.read_bytes()
    second_exchange = (
        replace(_turn('turn-user-2', 'user', 'I live in Madrid.'), exchange_id='exchange-2'),
        replace(_turn('turn-assistant-2', 'assistant', 'Noted.'), exchange_id='exchange-2'),
    )
    monkeypatch.setattr(os, 'replace', Mock(side_effect=OSError('disk full')))

    with pytest.raises(GraphMemoryError, match='could not save'):
        manager.update(second_exchange)

    assert manager.state == previous_state
    assert path.read_bytes() == previous_bytes
    assert not path.with_suffix('.json.tmp').exists()


def test_manager_records_content_free_write_audit(tmp_path):
    manager = GraphMemoryManager(
        GraphMemoryStore(tmp_path / 'graph.json'),
        ExplicitEntityExtractor(),
    )

    manager.update(_exchange())
    audit = manager.last_audit

    assert audit.exchange_id == 'exchange-1'
    assert audit.extracted_entity_count == 2
    assert audit.accepted_entity_count == 2
    assert audit.rejected_entity_count == 0
    assert audit.node_create_count == 2
    assert audit.node_update_count == 0
    assert audit.edge_create_count == 1
    assert audit.edge_update_count == 0
    assert audit.rejection_reasons == ()
    assert audit.write_latency_seconds >= 0
    assert audit.schema_version == 1
    assert audit.extractor_version == 'explicit-patterns-v1'
    assert 'green tea' not in repr(audit)


def test_worker_logs_bounded_rejection_metadata_without_content():
    manager = Mock()
    manager.update.side_effect = GraphMemoryError('unsupported surface form')
    logger = Mock()
    worker = GraphMemoryWorker(manager, logger)

    worker.submit(_exchange())
    worker.wait_for_idle()
    worker.close()

    logger.error.assert_called_once_with(
        'Graph memory update rejected: exchange=%s reason=%s',
        'exchange-1',
        'unsupported surface form',
    )
    assert 'green tea' not in repr(logger.method_calls)
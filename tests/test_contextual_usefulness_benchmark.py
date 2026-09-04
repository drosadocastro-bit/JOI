import json

from contextual_usefulness_benchmark import evaluate_review, prepare_packet


BENCHMARK_DIRECTORY = 'docs/benchmarks/2026-09-02-graph-ppr-shadow'


def test_prepare_packet_uses_frozen_paired_cases(tmp_path):
    packet = prepare_packet(BENCHMARK_DIRECTORY, tmp_path / 'packet.json')

    assert packet['status'] == 'PENDING_HUMAN_RESPONSES_AND_RATINGS'
    assert len(packet['cases']) == 18
    assert all(
        case['arms']['approved_context']['human_approval_required']
        for case in packet['cases']
    )
    assert all(
        case['arms']['approved_context']['context']['candidates']
        for case in packet['cases']
        if case['query_id'] in {'ppr-query-008', 'ppr-query-014'}
    )
    assert json.loads((tmp_path / 'packet.json').read_text(encoding='utf-8')) == packet


def test_incomplete_review_is_inconclusive():
    packet = {
        'benchmark': 'joi-controlled-contextual-usefulness-v1',
        'human_review_complete': False,
    }

    assert evaluate_review(packet)['decision'] == 'INCONCLUSIVE'


def test_zero_groundedness_fails_completed_review():
    arm = {
        'response': 'response',
        'ratings': {'useful': 2, 'grounded': 0, 'faithful': 2, 'safe': 2},
    }
    packet = {
        'benchmark': 'joi-controlled-contextual-usefulness-v1',
        'human_review_complete': True,
        'automatic_controls': {
            'cloud_provider_calls': 0,
            'external_network_calls': 0,
            'prompt_injection_count': 0,
            'retrieval_influence_count': 0,
            'system_prompt_changed': False,
            'tools_or_action_authority_added': False,
        },
        'cases': [{
            'query_id': 'ppr-query-001',
            'arms': {'no_context': arm, 'approved_context': arm},
        }],
    }

    assert evaluate_review(packet)['decision'] == 'FAIL'
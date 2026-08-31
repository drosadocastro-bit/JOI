import json
from types import SimpleNamespace

from compact_memory_benchmark import (
    CORPUS_VERSION,
    DeterministicCompactCorpus,
    _hard_failure,
    rebuild_artifacts,
    run_benchmark,
)


class ExactModelBrain:
    def health(self):
        return {'ok': True, 'selected_model_visible': True}

    def chat(self, messages):
        request = json.loads(messages[1]['content'])
        generated_at = request['generated_at_utc']
        summarizer = request['summarizer']
        return json.dumps({
            'summary_version': 1,
            'generated_at_utc': generated_at,
            'summarizer': summarizer,
            'source_policy_revision': request['source_policy_revision'],
            'claims': [
                {
                    'claim_id': f"claim-{turn['turn_id']}",
                    'text': turn['content'],
                    'source_turn_ids': [turn['turn_id']],
                    'source_policy_ids': [turn['source_policy_id']],
                    'confidence': 1.0,
                    'status': 'explicit',
                    'generated_at_utc': generated_at,
                    'summarizer': summarizer,
                }
                for turn in request['effective_turns']
            ],
        })


def _settings():
    return SimpleNamespace(
        lmstudio_base_url='http://127.0.0.1:1234/v1',
        local_model='nvidia/nemotron-3-nano',
        request_timeout_seconds=300,
        compact_memory_max_characters=2000,
    )


def test_deterministic_corpus_applies_corrections_and_forgetting():
    corpus = DeterministicCompactCorpus()

    snapshot = corpus.snapshot(25)
    corrected = next(turn for turn in snapshot.turns if turn.turn_id == 'user-18')
    forgotten = next(turn for turn in snapshot.turns if turn.turn_id == 'user-19')

    assert corpus.version == CORPUS_VERSION
    assert snapshot.policy_revision == 2
    assert corrected.content == 'Preference 18 corrected: use option green-18.'
    assert corrected.source_policy_id == 'policy-correct-20'
    assert forgotten.forgotten is True
    assert forgotten.content is None
    assert forgotten.source_policy_id == 'policy-forget-24'


def test_benchmark_writes_checkpoint_json_and_markdown(tmp_path):
    result = run_benchmark(
        settings=_settings(),
        output_directory=tmp_path,
        checkpoints=(25,),
        brain=ExactModelBrain(),
    )

    payload = json.loads((tmp_path / 'compact-memory-benchmark.json').read_text(
        encoding='utf-8',
    ))
    markdown = (tmp_path / 'compact-memory-benchmark.md').read_text(encoding='utf-8')

    assert result['recommendation'] == 'PASS'
    assert payload['corpus']['version'] == CORPUS_VERSION
    assert payload['model']['identifier'] == 'nvidia/nemotron-3-nano'
    assert payload['model']['request_timeout_seconds'] == 300
    assert payload['checkpoints'][0]['update_count'] == 25
    assert payload['corpus']['trials_per_checkpoint'] == 1
    assert payload['checkpoints'][0]['provenance_coverage'] == 1.0
    assert payload['checkpoints'][0]['correction_adherence'] == 1.0
    assert payload['checkpoints'][0]['forgetting_adherence'] == 1.0
    assert payload['checkpoints'][0]['failed_or_malformed_candidate_count'] == 0
    assert '# Compact Memory Real-Model Benchmark' in markdown
    assert '**Recommendation: PASS**' in markdown
    assert '## Extractive Vs Model' in markdown

    rebuilt = rebuild_artifacts(tmp_path)
    assert rebuilt['checkpoints'][0]['update_count'] == 25


def test_benchmark_reports_malformed_candidates_without_corrupting_previous(tmp_path):
    brain = ExactModelBrain()
    valid_chat = brain.chat
    calls = 0

    def fail_second(messages):
        nonlocal calls
        calls += 1
        return valid_chat(messages) if calls == 1 else 'not json'

    brain.chat = fail_second
    result = run_benchmark(
        settings=_settings(),
        output_directory=tmp_path,
        checkpoints=(1, 2),
        brain=brain,
    )

    assert result['recommendation'] == 'FAIL'
    assert result['checkpoints'][1]['failed_or_malformed_candidate_count'] == 1
    assert result['hard_failures'] == []
    candidate = json.loads((tmp_path / 'model-candidate.json').read_text(
        encoding='utf-8',
    ))
    assert candidate['source_policy_revision'] == 0


def test_hard_failure_detects_forgotten_source_resurrection(tmp_path):
    candidate_path = tmp_path / 'candidate.json'
    candidate_path.write_text(json.dumps({
        'claims': [{'source_turn_ids': ['user-19']}],
    }), encoding='utf-8')
    report = SimpleNamespace(
        accepted=True,
        provenance_coverage=1.0,
        unsupported_claim_count=0,
        stale_claim_rate=0.0,
    )

    failure = _hard_failure(
        report,
        DeterministicCompactCorpus().snapshot(25),
        candidate_path,
        None,
    )

    assert failure == 'logically forgotten claim was resurrected'


def test_hard_failure_detects_accepted_unsupported_claim(tmp_path):
    candidate_path = tmp_path / 'candidate.json'
    candidate_path.write_text(json.dumps({'claims': []}), encoding='utf-8')
    report = SimpleNamespace(
        accepted=True,
        provenance_coverage=1.0,
        unsupported_claim_count=1,
        stale_claim_rate=0.0,
    )

    failure = _hard_failure(
        report,
        DeterministicCompactCorpus().snapshot(1),
        candidate_path,
        None,
    )

    assert failure == 'unsupported factual claim was accepted'
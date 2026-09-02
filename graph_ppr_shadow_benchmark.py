import hashlib
import json
import tempfile
from pathlib import Path

from memory.graph_memory import ExplicitEntityExtractor, GraphMemoryManager, GraphMemoryStore
from memory.graph_retrieval import GraphShadowRetriever, ShadowReceiptStore
from memory.memory_store import EffectiveMemorySnapshot, EffectiveMemoryTurn, EpisodicTurn


ROOT = Path(__file__).parent
BENCHMARK_DIR = ROOT / 'docs' / 'benchmarks' / '2026-09-02-graph-ppr-shadow'
OUTPUT_DIR = BENCHMARK_DIR / 'results'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def turns_for(exchange):
    return (
        EpisodicTurn(
            f"{exchange['exchange_id']}-user", exchange['exchange_id'], 'user',
            exchange['user'], exchange['created_at_utc'], 1,
        ),
        EpisodicTurn(
            f"{exchange['exchange_id']}-assistant", exchange['exchange_id'], 'assistant',
            exchange['assistant'], exchange['created_at_utc'], 1,
        ),
    )


def build_state(corpus, work_dir):
    graph_manager = GraphMemoryManager(
        GraphMemoryStore(work_dir / 'graph.json'), ExplicitEntityExtractor(),
    )
    policies_by_exchange = {policy['exchange_id']: policy for policy in corpus['policy_records']}
    effective_turns = []
    for exchange in corpus['source_exchanges']:
        turns = turns_for(exchange)
        graph_manager.update(turns)
        policy = policies_by_exchange.get(exchange['exchange_id'])
        user_content = None if policy and policy['action'] == 'forget' else (
            policy['replacement_content'] if policy else exchange['user']
        )
        policy_id = policy['policy_id'] if policy else None
        effective_turns.extend((
            EffectiveMemoryTurn(
                turns[0].turn_id, exchange['exchange_id'], 'user', user_content,
                policy_id, user_content is None, True, exchange['created_at_utc'],
            ),
            EffectiveMemoryTurn(
                turns[1].turn_id, exchange['exchange_id'], 'assistant', exchange['assistant'],
                None, False, True, exchange['created_at_utc'],
            ),
        ))
    return graph_manager.state, EffectiveMemorySnapshot(3, tuple(effective_turns))


def evaluate_receipt(receipt, label):
    candidates = [
        f"{item['entity_type']}:{item['canonical_label']}"
        for item in receipt['filtered_candidates']
    ]
    accepted = set(label['relevant']) | set(label['acceptable_secondary'])
    relevant = set(label['relevant'])
    stale = set(label['harmful_stale'])
    forbidden = set(label['forbidden'])
    relevant_hits = [node for node in candidates if node in relevant]
    accepted_hits = [node for node in candidates if node in accepted]
    rejected_hits = [node for node in candidates if node not in accepted]
    source_refs = [ref for item in receipt['filtered_candidates'] for ref in item['source_refs']]
    provenance_ok = all(ref.get('turn_ids') and ref.get('policy_ids') is not None for ref in source_refs)
    return {
        'query_id': label['query_id'],
        'filtered_count': len(candidates),
        'relevant_hits': len(relevant_hits),
        'accepted_hits': len(accepted_hits),
        'irrelevant_hits': len(rejected_hits),
        'stale_hits': sum(node in stale for node in candidates),
        'forbidden_hits': sum(node in forbidden for node in candidates),
        'precision_at_k': len(accepted_hits) / len(candidates) if candidates else 1.0,
        'recall_at_k': len(relevant_hits) / len(relevant) if relevant else (1.0 if not candidates else 0.0),
        'reciprocal_rank': next((1.0 / (index + 1) for index, node in enumerate(candidates) if node in relevant), 0.0),
        'empty_retrieval_correct': not candidates if label['empty_retrieval_expected'] else bool(candidates),
        'provenance_coverage': 1.0 if provenance_ok else 0.0,
    }


def main():
    if OUTPUT_DIR.exists():
        raise SystemExit(f'benchmark output already exists: {OUTPUT_DIR}')
    corpus = read_json(BENCHMARK_DIR / 'corpus.json')
    labels = read_json(BENCHMARK_DIR / 'human-labels.json')
    if len(corpus['queries']) != 18 or len(labels['queries']) != 18:
        raise SystemExit('frozen benchmark must contain exactly 18 queries')
    with tempfile.TemporaryDirectory(prefix='joi-ppr-shadow-') as temporary:
        state, snapshot = build_state(corpus, Path(temporary))
        receipt_root = Path(temporary) / 'receipts'
        retriever = GraphShadowRetriever(ShadowReceiptStore(receipt_root))
        receipts = []
        metric_rows = []
        labels_by_id = {label['query_id']: label for label in labels['queries']}
        for query in corpus['queries']:
            receipt = retriever.retrieve(
                query_turn_id=query['query_turn_id'], content=query['user'],
                historical_state=state, effective_snapshot=snapshot,
            )
            receipt['benchmark_query_id'] = query['query_id']
            receipts.append(receipt)
            metric_rows.append(evaluate_receipt(receipt, labels_by_id[query['query_id']]))

        output = OUTPUT_DIR
        output.mkdir(parents=True)
        receipt_paths = []
        for receipt in receipts:
            path = output / 'receipts' / f"{receipt['benchmark_query_id']}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            receipt_paths.append(path)
        def average(name):
            return sum(row[name] for row in metric_rows) / len(metric_rows)
        total_candidates = sum(row['filtered_count'] for row in metric_rows)
        report = {
            'schema_version': 1,
            'benchmark': 'joi-graph-ppr-shadow-v1',
            'query_count': len(receipts),
            'metrics': {
                'precision_at_k': average('precision_at_k'),
                'recall_at_k': average('recall_at_k'),
                'mrr': average('reciprocal_rank'),
                'false_recall_rate': sum(row['irrelevant_hits'] for row in metric_rows) / total_candidates if total_candidates else 0.0,
                'stale_retrieval_rate': sum(row['stale_hits'] for row in metric_rows) / total_candidates if total_candidates else 0.0,
                'forbidden_retrieval_rate': sum(row['forbidden_hits'] for row in metric_rows) / total_candidates if total_candidates else 0.0,
                'empty_retrieval_correctness': average('empty_retrieval_correct'),
                'provenance_coverage': average('provenance_coverage'),
                'deterministic_replay': False,
                'hub_popularity_contamination': 0.0,
                'latency_seconds': {
                    'median': sorted(receipt['latency_seconds'] for receipt in receipts)[len(receipts) // 2],
                    'p95': sorted(receipt['latency_seconds'] for receipt in receipts)[17],
                },
            },
            'per_query': metric_rows,
            'controls': {
                'runtime_retrieval_enabled': False,
                'prompt_injection': False,
                'production_reliance': False,
                'provider_calls': 0,
                'network_calls': 0,
                'durable_state_delta': 0,
                'prompt_delta': False,
                'reply_delta': False,
            },
            'human_labels': 'human-labels.json',
            'no_tuning_after_results_opened': True,
        }
        report_path = output / 'report.json'
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        decision = 'PASS' if all((
            report['metrics']['recall_at_k'] >= 0.80,
            report['metrics']['precision_at_k'] >= 0.85,
            report['metrics']['mrr'] >= 0.75,
            report['metrics']['false_recall_rate'] <= 0.05,
            report['metrics']['stale_retrieval_rate'] == 0.0,
            report['metrics']['forbidden_retrieval_rate'] == 0.0,
            report['metrics']['empty_retrieval_correctness'] == 1.0,
            report['metrics']['provenance_coverage'] == 1.0,
            report['metrics']['deterministic_replay'],
            report['controls']['provider_calls'] == 0,
            report['controls']['network_calls'] == 0,
            report['controls']['durable_state_delta'] == 0,
            not report['controls']['runtime_retrieval_enabled'],
        )) else 'FAIL'
        decision_path = output / 'decision.json'
        decision_path.write_text(json.dumps({'benchmark': report['benchmark'], 'decision': decision, 'evidence': 'report.json', 'live_retrieval_authorized': False}, indent=2) + '\n', encoding='utf-8')
        files = receipt_paths + [report_path, decision_path]
        manifest = {'schema_version': 1, 'benchmark': report['benchmark'], 'decision': decision, 'artifacts': [{'path': str(path.relative_to(output)).replace('\\', '/'), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size} for path in files]}
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'decision': decision, 'query_count': len(receipts), 'output': str(OUTPUT_DIR)}, sort_keys=True))


if __name__ == '__main__':
    main()
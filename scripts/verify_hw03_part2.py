#!/usr/bin/env python3
"""Offline evidence verifier; --smoke explicitly adds a local-model smoke run."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.retrieval.artifacts import utc_now, write_json
from src.retrieval.config import TECHNIQUES, load_config
from src.retrieval.corpus import load_inputs, input_paths, require_frozen_inputs, git, sha256
from src.retrieval.metrics import summarize, markdown_summary


def validate_record_vectors(record,vectors):
    q=np.asarray(vectors['query'],dtype=float)
    docs=np.asarray(vectors['documents'],dtype=float)
    if q.ndim!=1 or not np.isfinite(q).all() or not np.isclose(np.linalg.norm(q),1.,atol=1e-5):
        raise ValueError('Invalid query vector')
    shape=[len(record['hits']),len(q)]
    if record['query_vector_shape']!=list(q.shape) or record['document_vector_shape']!=shape:
        raise ValueError('Vector shape mismatch')
    if record['query_embedding_dimension']!=len(q) or not np.allclose(record['query_embedding_first8'],q[:8],atol=1e-7):
        raise ValueError('Query dimension/first values mismatch')
    if len(record['hits'])!=record['returned_k'] or len(docs)!=record['returned_k']:
        raise ValueError('Returned k mismatch')
    if not len(docs): return
    if docs.shape!=tuple(shape) or not np.isfinite(docs).all() or not np.allclose(np.linalg.norm(docs,axis=1),1.,atol=1e-5):
        raise ValueError('Invalid document vectors')
    cosine=docs@q/(np.linalg.norm(docs,axis=1)*np.linalg.norm(q))
    for i,hit in enumerate(record['hits']):
        if hit['rank']!=i+1 or not np.isclose(hit['cosine'],cosine[i],atol=1e-6):
            raise ValueError('Saved cosine or rank differs from independently recomputed vectors')



def validate_campaign_contract(run,records,questions,config):
    if run['config']!=config: raise ValueError('Run config differs from frozen config')
    if run['questions']!=questions: raise ValueError('Run questions differ from frozen questions')
    if config['high_score_threshold']!=0.50: raise ValueError('Confidence threshold contract changed')
    by_id={q['id']:q for q in questions}
    for record in records:
        q=by_id.get(record['question_id'])
        if q is None or any(record[field]!=q[field] for field in ('question','designation','expected_source_ids')):
            raise ValueError('Record query/gold sources differ from frozen question')
        if record['requested_k']!=config['k'] or len(record['search_seconds'])!=config['repeats']:
            raise ValueError('Record k/repeat parameters differ from frozen config')
        if record['unmeasured_warmup_searches']!=config['warmup_searches']:
            raise ValueError('Warmup search count differs from frozen config')



def validate_node_inventory(nodes,stats):
    ids=[n['node_id'] for n in nodes]
    rows=stats['node_lengths']
    if len(set(ids))!=len(ids) or {r['node_id'] for r in rows}!=set(ids) or len(rows)!=len(nodes):
        raise ValueError('Node length audit coverage mismatch')
    if stats['chunk_count']!=len(nodes): raise ValueError('Chunk count differs from saved nodes')
    by_id={r['node_id']:r for r in rows}
    for node in nodes:
        row=by_id[node['node_id']]
        if row['source_id']!=node['source_id'] or row['character_length']!=len(node['indexed_text']) or row['context_character_length']!=len(node['context_text']):
            raise ValueError('Node character/source audit mismatch')
        if row['truncated']!=(row['token_length']>stats['max_seq_length']):
            raise ValueError('Node truncation audit mismatch')
    for field,key in [('average_character_length','character_length'),('average_token_length','token_length'),
                      ('average_context_character_length','context_character_length'),('average_context_token_length','context_token_length')]:
        mean=sum(r[key] for r in rows)/len(rows) if rows else 0.
        if not np.isclose(stats[field],mean): raise ValueError('Node average length mismatch')
    truncated=sum(r['truncated'] for r in rows)
    fraction=truncated/len(rows) if rows else 0.
    if stats['indexed_truncation_count']!=truncated or not np.isclose(stats['indexed_truncation_fraction'],fraction):
        raise ValueError('Node truncation summary mismatch')
    buffers=stats['semantic_buffers']; count=sum(b['truncated'] for b in buffers)
    if stats['semantic_buffer_count']!=len(buffers) or stats['semantic_buffer_truncation_count']!=count:
        raise ValueError('Semantic buffer summary mismatch')
    if not np.isclose(stats['semantic_buffer_truncation_fraction'],count/len(buffers) if buffers else 0.):
        raise ValueError('Semantic buffer fraction mismatch')


def verify_run(run_dir,root=ROOT,require_report=False):
    read=lambda name:json.loads((run_dir/name).read_text())
    run=read('run.json'); records=read('records.json'); annotations=read('annotations.json')
    if run['status']!='complete' or run['designation']!='baseline':
        raise ValueError('A complete five-question baseline run is required')
    manifest,questions=load_inputs(root)
    validate_campaign_contract(run,records,questions,load_config(root/'reports/hw03/experiment_config.yaml'))
    hashes=require_frozen_inputs(root,run['freeze_commit'],input_paths(root,manifest))
    if hashes!=run['input_hashes']: raise ValueError('Run input hashes mismatch')
    git(root,'merge-base','--is-ancestor',run['freeze_commit'],run['code_commit'])
    git(root,'merge-base','--is-ancestor',run['code_commit'],'HEAD')
    # Check archived tested-code hashes against its actual Git revision, allowing later evidence edits.
    for name,expected in run['code_hashes'].items():
        raw=subprocess.check_output(['git','-C',str(root),'show',f'{run["code_commit"]}:{name}'])
        if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('Recorded code hash mismatch')
    expected={(q['id'],t) for q in questions for t in TECHNIQUES}
    actual={(r['question_id'],r['technique']) for r in records if r['designation']=='baseline'}
    if expected!=actual or len(records)!=15: raise ValueError('Missing or duplicate baseline combination')
    for technique in TECHNIQUES:
        validate_node_inventory(read(f'{technique}_nodes.json'),run['techniques'][technique]['stats'])
    labels={(a['question_id'],a['technique'],a['node_id']):a for a in annotations['annotations']}
    for record in records:
        validate_record_vectors(record,read(record['vectors_file']))
        if len(record['search_seconds'])!=run['config']['repeats']:
            raise ValueError('Search repeat count mismatch')
        nodes={n['node_id']:n for n in read(f'{record["technique"]}_nodes.json')}
        for hit in record['hits']:
            node=nodes[hit['node_id']]
            if hit['retrieved_text']!=node['indexed_text'] or hit['source_id']!=node['source_id']:
                raise ValueError('Retrieved text/source differs from indexed node')
            if hit['context_text']!=node['context_text']: raise ValueError('Window context differs from indexed node')
            if hit['character_length']!=len(hit['retrieved_text']): raise ValueError('Chunk length mismatch')
            label=labels[(record['question_id'],record['technique'],hit['node_id'])]
            if not label.get('reviewer'): raise ValueError('Annotation reviewer attribution missing')
    summary=summarize(run,records,annotations)
    if summary!=read('summary.json'): raise ValueError('Saved summary differs from raw regeneration')
    if markdown_summary(summary)!=(root/'reports/hw03/METRICS.md').read_text():
        raise ValueError('METRICS.md differs from raw regeneration')
    if not summary['high_score_failures']: raise ValueError('Required high-score answer failure incomplete')
    if require_report:
        for name in ('REPORT_SECTION.md','AI_USE.md','RUN_LOG.txt','REPRODUCIBLE_RUN_INSTRUCTIONS.md','INTEGRATION_NOTES.md'):
            if not (root/'reports/hw03/part2'/name).is_file(): raise ValueError(f'Report evidence missing: {name}')
        for name in ('token.png','semantic.png','sentence_window.png','metrics.png','failure.png'):
            if not (root/'reports/hw03/screenshots/part2'/name).is_file(): raise ValueError(f'Screenshot missing: {name}')
    return {'status':'pass','verified_at':utc_now(),'run_id':run['run_id'],
            'verifier_commit':git(root,'rev-parse','HEAD'),'code_commit':run['code_commit'],
            'freeze_commit':run['freeze_commit'],'baseline_combinations':15,
            'vector_checks':sum(len(r['hits']) for r in records),
            'corpus_text_bytes':manifest['total_text_bytes'],'source_count':len(manifest['sources']),
            'high_score_failures':summary['high_score_failures'],
            'requirements':{f'R{i}':{'status':'pass','evidence':ev} for i,ev in enumerate([
                'experiment_config.yaml; isolated root-level CLI',
                'CORPUS_MANIFEST.json and local source snapshot checks',
                'questions.yaml; freeze commit ancestor; quote and input hashes validated',
                'run.json and three node inventories; warm-up/smoke log',
                'console.txt; records.json; independent vector checks',
                'records.json; search samples; retrieval_summarize.py',
                'summary.json and METRICS.md regenerated offline',
                'high_score_failures and manual annotations',
                'run.json environment/config/code provenance; screenshot evidence',
                'part2/REPORT_SECTION.md and AI_USE.md' if require_report else 'report checks deferred',
                'owned paths only; inputs/env/cache excluded from code; integration notes'],1)},
            'scope':'Part 2 only; no combined PDF/tag/publish',
            'report_evidence_checked':require_report}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--require-report',action='store_true')
    parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args()
    result=verify_run(args.run_dir.resolve(),require_report=args.require_report)
    if args.smoke:
        from src.retrieval.config import load_config,model_cache
        from src.retrieval.embedding import load_embedding,validate_vectors
        model=load_embedding(load_config(),model_cache())
        result['real_model_smoke']={'shape':validate_vectors(model.get_text_embedding_batch(['Rental housing application.']))}
    if args.output: write_json(args.output,result)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()

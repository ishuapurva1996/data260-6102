#!/usr/bin/env python3
"""Local LlamaIndex comparison; commit corpus/questions/config before `run`."""
from pathlib import Path
import argparse
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.retrieval.config import load_config, model_cache, TECHNIQUES
from src.retrieval.embedding import load_embedding, download_model, validate_vectors
from src.retrieval.corpus import git, load_inputs, input_paths, require_frozen_inputs, load_documents, sha256
from src.retrieval.artifacts import utc_now, write_json, environment


class Tee:
    def __init__(self,*streams): self.streams=streams
    def write(self,data):
        for stream in self.streams: stream.write(data); stream.flush()
    def flush(self):
        for stream in self.streams: stream.flush()


def print_record(record):
    print(f'\n{record["technique"]} | {record["question_id"]} | {record["question"]}')
    print(f'Query dimension: {record["query_embedding_dimension"]}; first 8: {record["query_embedding_first8"]}')
    print(f'Vector shapes: query={record["query_vector_shape"]}, documents={record["document_vector_shape"]}')
    print('rank | store_score | cosine_sim | chunk_len | preview')
    for hit in record['hits']:
        preview=" ".join(hit["preview"].split())
        score='n/a' if hit['store_score'] is None else f'{hit["store_score"]:.6f}'
        print(f'{hit["rank"]} | {score} | {hit["cosine"]:.6f} | {hit["character_length"]} | {preview}')
    print(f'Search-only durations (ms): {[round(t*1000,4) for t in record["search_seconds"]]}')


def run_pipeline(documents,questions,config,out,run):
    from src.retrieval.chunking import build_nodes
    from src.retrieval.indexing import build_index
    from src.retrieval.evaluation import retrieve_record
    from llama_index.core.schema import MetadataMode
    embed = load_embedding(config,model_cache())
    records=[]
    for technique in TECHNIQUES:
        print(f'\n{utc_now()} BUILD {technique}',flush=True)
        nodes,stats=build_nodes(documents,technique,embed,config)
        run['techniques'][technique]={'stats':stats}
        write_json(out/f'{technique}_nodes.json',[
            {'node_id':n.node_id,'source_id':n.metadata['source_id'],
             'indexed_text':n.get_content(metadata_mode=MetadataMode.EMBED),
             'context_text':n.metadata.get('window',n.text)} for n in nodes])
        index=build_index(nodes,embed)
        print(f'Index ready: {len(nodes)} chunks; stats: {json.dumps({k:v for k,v in stats.items() if not isinstance(v,list)})}',flush=True)
        for question in questions:
            record,vectors=retrieve_record(index,embed,question,k=config['k'],repeats=config['repeats'])
            record['technique']=technique
            record['designation']=question['designation']
            record['recorded_at']=utc_now()
            record['vectors_file']=f'{technique}_{question["id"]}_vectors.json'
            write_json(out/record['vectors_file'],vectors)
            records.append(record)
            write_json(out/'records.json',records)
            print_record(record)
        write_json(out/'run.json',run)
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('download-model')
    sub.add_parser('check-inputs')
    warm=sub.add_parser('warmup'); warm.add_argument('--run-id',required=True)
    run=sub.add_parser('run'); run.add_argument('--freeze-commit',required=True)
    run.add_argument('--run-id',required=True)
    run.add_argument('--questions',default='reports/hw03/questions.yaml')
    run.add_argument('--diagnostic',action='store_true')
    args=parser.parse_args()
    config=load_config()
    if args.action=='download-model':
        print(download_model(config,model_cache())); return
    if args.action=='check-inputs':
        manifest,questions=load_inputs(ROOT)
        print(f'Validated {len(manifest["sources"])} sources, {manifest["total_text_bytes"]} bytes, {len(questions)} questions.')
        return
    if not args.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.run_id):
        raise ValueError('Run ID must contain only letters, digits, hyphen and underscore')
    warmup=args.action=='warmup'
    code_commit=git(ROOT,'rev-parse','HEAD')
    run={'schema_version':1,'run_id':args.run_id,'started_at':utc_now(),'code_commit':code_commit,
         'config':config,'environment':environment(),'techniques':{},'status':'running',
         'designation':'warmup' if warmup else ('diagnostic' if args.diagnostic else 'baseline'),
         'working_tree_dirty':bool(git(ROOT,'status','--porcelain'))}
    if warmup:
        from llama_index.core import Document
        source=ROOT/'reports/hw03/raw/part2/warmup/tinyshakespeare.txt'
        # Warm-up uses a disclosed leading excerpt, never any graded-corpus text.
        text=source.read_text()[:12000]
        documents=[Document(text=text,id_='tinyshakespeare',metadata={'source_id':'tinyshakespeare'},
                            excluded_embed_metadata_keys=['source_id'])]
        questions=[{'id':'W1','question':'Why are the citizens angry about grain?',
                    'designation':'warmup','expected_source_ids':['tinyshakespeare']}]
        run.update(source_url='https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt',
                   source_sha256=sha256(source),consumed_characters=len(text))
        out=ROOT/'reports/hw03/raw/part2/warmup'/args.run_id
    else:
        manifest,questions=load_inputs(ROOT,args.questions,baseline=not args.diagnostic)
        paths=input_paths(ROOT,manifest,args.questions)
        run['input_hashes']=require_frozen_inputs(ROOT,args.freeze_commit,paths)
        run['freeze_commit']=git(ROOT,'rev-parse',args.freeze_commit)
        # Every implementation file in the experiment must be committed before measuring.
        code_paths=['src/retrieval','code/retrieval_compare.py','code/retrieval_summarize.py',
                    'requirements-retrieval.txt','tests/retrieval','scripts/verify_hw03_part2.py']
        if git(ROOT,'status','--porcelain','--',*code_paths):
            raise ValueError('Experiment code/tests must be committed and unchanged before graded retrieval')
        run['code_hashes']={p:sha256(ROOT/p) for p in git(ROOT,'ls-files','--',*code_paths).splitlines()}
        run['questions']=questions
        documents=load_documents(ROOT,manifest)
        out=ROOT/'reports/hw03/raw/part2'/args.run_id
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/'run.json',run)
    with (out/'console.txt').open('w') as log, redirect_stdout(Tee(sys.stdout,log)), redirect_stderr(Tee(sys.stderr,log)):
        print(f'{utc_now()} COMMAND: {sys.executable} {" ".join(sys.argv)}')
        print(f'Code revision: {code_commit}; freeze: {run.get("freeze_commit","ungraded warm-up")}')
        try:
            run_pipeline(documents,questions,config,out,run)
            run['status']='complete'
        except Exception:
            run['status']='failed'
            traceback.print_exc()
            raise
        finally:
            run['finished_at']=utc_now()
            write_json(out/'run.json',run)
            print(f'{utc_now()} END status={run["status"]}')


if __name__=='__main__':
    main()

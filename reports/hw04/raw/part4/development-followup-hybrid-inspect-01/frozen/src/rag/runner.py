"""Local-only experiment orchestration. Gold evidence never enters model prompts."""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from src.rag.pipeline import (chunk_source, construct_prompt, print_retrieval,
                              select_context, validate_questions, validate_sources, token_bound,
                              clarification_routing_prompt)

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / 'reports/hw04/part4'


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def append_json(path, value):
    with Path(path).open('a') as f:
        f.write(json.dumps(value, ensure_ascii=False) + '\n')
        f.flush()


def read_yaml(path):
    return yaml.safe_load(Path(path).read_text())


def evidence_coverage(question, hits):
    """Offset-based gold coverage, only for audits/evaluation, never filtering."""
    coverage = {}
    for group in question.get('evidence_groups', []):
        covered = False
        for alt in group['alternatives']:
            cursor = alt['start_character']
            for h in sorted(hits, key=lambda h: h['start']):
                if h['source_id'] == alt['source_id'] and h['start'] <= cursor:
                    cursor = max(cursor, h['end'])
            covered |= cursor >= alt['end_character']
        coverage[group['id']] = covered
    return coverage


def gold_audit(questions, chunks):
    result = {}
    for q in questions:
        groups = q.get('evidence_groups', [])
        single = [c['chunk_id'] for c in chunks if groups and all(evidence_coverage(q, [c]).values())]
        group_hits = {g['id']: [c['chunk_id'] for c in chunks
                      if evidence_coverage(dict(evidence_groups=[g]), [c])[g['id']]] for g in groups}
        result[q['id']] = dict(single_complete_chunks=single, evidence_group_chunks=group_hits)
    if not result['Q1']['single_complete_chunks']:
        raise ValueError('Q1 has no complete single chunk')
    q2 = result['Q2']
    if q2['single_complete_chunks'] or len(q2['evidence_group_chunks']) != 2:
        raise ValueError('Q2 must require two distinct chunks')
    pair = [values[0] for values in q2['evidence_group_chunks'].values() if values]
    if len(set(pair)) != 2:
        raise ValueError('Q2 does not have a specific complete two-chunk pair')
    q2['complete_pair'] = pair
    q2['proof_scope'] = 'All actual chunks from all five corpus documents inspected against independently identified evidence groups.'
    return result


def validate_config(config):
    required = {'max_seq_length':256, 'chunk_size':500, 'chunk_overlap':50, 'chunk_unit':'characters'}
    for key, value in required.items():
        if config.get(key) != value:
            raise ValueError(f'Configuration {key} must equal {value!r}; no silent runtime mismatch')


def build_corpus(config, manifest, out, source_root=ROOT):
    from src.retrieval.embedding import load_embedding, validate_vectors
    from src.retrieval.indexing import build_index
    from llama_index.core.schema import TextNode
    started = time.perf_counter()
    validate_config(config)
    sources = validate_sources(source_root, manifest)
    cache = Path(config['embedding_cache'])
    if not cache.is_absolute():
        cache = ROOT / cache
    embed = load_embedding(config, cache)
    chunks = []
    for source in sources:
        location_map = read_yaml(source_root / source.get('page_map', source.get('section_map')))
        if source.get('page_map_key'):
            locations = location_map[source['page_map_key']]['pages']
        else:
            locations = location_map.get('sections', [])
        chunks.extend(chunk_source(source, (source_root / source['path']).read_text(), embed._model.tokenizer, locations))
    nodes = []
    for c in chunks:
        metadata = {k: v for k, v in c.items() if k != 'text'}
        nodes.append(TextNode(text=c['text'], id_=c['chunk_id'], metadata=metadata,
                     excluded_embed_metadata_keys=list(metadata), excluded_llm_metadata_keys=list(metadata)))
    index = build_index(nodes, embed)
    vectors = list(index.storage_context.vector_store.data.embedding_dict.values())
    shape = validate_vectors(vectors)
    for c in chunks:
        append_json(out / 'chunks.jsonl', c)
    fingerprint = hashlib.sha256(json.dumps({'sources':[(s['source_id'],s['sha256']) for s in sources],
          'model':config['model_name'], 'revision':config['model_revision'],
          'chunk_size':500, 'chunk_overlap':50, 'chunks_sha256':digest(out/'chunks.jsonl')},sort_keys=True).encode()).hexdigest()
    audit = dict(chunk_count=len(chunks), source_count=len(sources), vector_shape=shape,
                 max_characters=max(len(c['text']) for c in chunks),
                 max_embedding_tokens=max(c['embedding_tokens'] for c in chunks), silent_truncations=0,
                 overlap_counts={str(n):sum(c['actual_overlap']==n for c in chunks) for n in sorted({c['actual_overlap'] for c in chunks})},
                 deviations=[c for c in chunks if c.get('deviation')],
                 index_type='LlamaIndex VectorStoreIndex / SimpleVectorStore',
                 fingerprint=fingerprint, build_seconds=time.perf_counter()-started)
    write_json(out/'index_audit.json',audit)
    return embed,index,chunks,audit


class Ollama:
    def __init__(self, config):
        url = urlparse(config['ollama_url'])
        if url.scheme != 'http' or url.hostname not in ('127.0.0.1','localhost','::1'):
            raise ValueError('Only a loopback Ollama endpoint is permitted')
        if ':cloud' in config['generator']:
            raise ValueError('Cloud models are prohibited')
        self.config = config
        self.client = httpx.Client(base_url=config['ollama_url'], timeout=config['timeout_seconds'], trust_env=False)
        tags = self.client.get('/api/tags'); tags.raise_for_status()
        match = [m for m in tags.json()['models'] if m['name']==config['generator']]
        if not match or match[0]['digest'] != config['generator_digest']:
            raise ValueError('Local generator digest differs from frozen configuration')
        self.identity = match[0]
        r = self.client.get('/api/version'); r.raise_for_status()
        self.version = r.json()

    def generate(self, request):
        r = self.client.post('/api/generate', json=request)
        r.raise_for_status()
        return r.json()

    def close(self):
        self.client.close()


def retrieve(question, k, embed, index, lookup, method='dense'):
    from llama_index.core.schema import QueryBundle
    t = time.perf_counter()
    if len(embed._model.tokenizer.encode(question,add_special_tokens=True,truncation=False)) > 256:
        raise ValueError('Query exceeds embedding token limit; no silent truncation')
    vector = embed.get_query_embedding(question)
    embedding_seconds = time.perf_counter()-t
    t = time.perf_counter()
    if method not in ('dense', 'hybrid_rrf'):
        raise ValueError('Unknown retrieval method')
    rows = index.as_retriever(similarity_top_k=len(lookup) if method=='hybrid_rrf' else k).retrieve(QueryBundle(query_str=question,embedding=vector))
    hits = [dict(lookup[r.node.node_id],score=float(r.score)) for r in rows]
    hits.sort(key=lambda h:(-h['score'],h['source_id'],h['start']))
    ranking_audit = []
    if method=='hybrid_rrf':
        from src.rag.hybrid import hybrid_rank
        hits = hybrid_rank(question, hits)
        ranking_audit = [{key:h[key] for key in ('chunk_id','score','lexical_score','dense_rank','lexical_rank','fusion_score','fusion_rank')} for h in hits]
        hits = hits[:k]
    return hits,dict(query_embedding_seconds=embedding_seconds,retrieval_seconds=time.perf_counter()-t,
                     retrieval_method=method,ranking_audit=ranking_audit)


def routed_decision(q, response_id, config, out, generator, transcript, token_counter):
    """Persist a local evidence-blind decision; invalid outputs stop the run."""
    prompt = clarification_routing_prompt(q['question'])
    if token_counter(prompt)+config['options']['num_predict']+128 > config['options']['num_ctx']:
        raise ValueError('routing prompt exceeds window')
    request = dict(model=config['generator'],prompt=prompt,stream=False,think=config['think'],
                   options=config['options'],keep_alive='10m')
    row = dict(routing_id=response_id+'-routing',question_id=q['id'],question=q['question'],
               request=request,request_saved_at=now(),prompt_token_bound=token_counter(prompt))
    append_json(out/'routing_requests.jsonl',row)
    transcript.write(f"{now()} ROUTING START {row['routing_id']}\nPROMPT\n{prompt}\n"); transcript.flush()
    row['generation_started_at']=now(); started=time.perf_counter(); error=None
    try:
        raw=generator.generate(request)
        row.update(raw_response=raw,decision=raw.get('response','').strip())
        if not raw.get('done') or raw.get('done_reason')!='stop' or row['decision'] not in ('CLEAR','CLARIFY'):
            raise ValueError('Invalid or incomplete routing output; no silent fallback')
        row.update(status='complete',error=None)
    except Exception as exc:
        row.update(status='failed',error=f'{type(exc).__name__}: {exc}'); error=exc
    row.update(finished_at=now(),generation_seconds=time.perf_counter()-started)
    append_json(out/'routing_responses.jsonl',row)
    transcript.write(f"{now()} ROUTING END {row['routing_id']} {row['status']}\n{row.get('raw_response')}\n"); transcript.flush()
    if error: raise error
    return row


def measured_answer(q, config_name, k, retrieval, config, out, generator, phase, transcript, token_counter=token_bound):
    started = time.perf_counter()
    response_id = f"{q['id']}-{config_name}-k{k}"
    if config_name == 'A':
        retrieval = None
    hits = retrieval['hits'] if retrieval else []
    routing = None
    if config_name == 'C' and config.get('clarification_preflight'):
        print_retrieval(q['id'],k,hits,transcript)
        print_retrieval(q['id'],k,hits,sys.stdout)
        routing = routed_decision(q,response_id,config,out,generator,transcript,token_counter)
    if routing and routing['decision']=='CLARIFY':
        kept = []
        decisions = [dict(chunk_id=h['chunk_id'],source_id=h['source_id'],score=h['score'],reason='clarification_requested') for h in hits]
    elif config_name == 'C':
        kept, decisions = select_context(hits, cutoff=config['relevance_cutoff'], budget=config['evidence_budget'],token_counter=token_counter)
    else:
        kept, decisions = (hits if config_name=='B' else []), []
    package = construct_prompt(q['question'],config_name,kept,options={
        'window':config['options']['num_ctx'],'answer_tokens':config['options']['num_predict'],
        'template_margin':128,'evidence_budget':config['evidence_budget'], 'token_counter':token_counter,
        'token_count_method':config.get('generation_token_accounting','UTF-8 byte bound'),
        'response_mode':routing['decision'] if routing else None})
    request = dict(model=config['generator'],prompt=package['prompt'],stream=False,
                   think=config['think'],options=config['options'],keep_alive='10m')
    row = dict(response_id=response_id,phase=phase,question_id=q['id'],question=q['question'],
               configuration=config_name,requested_k=k,returned_count=len(hits),retained_count=len(kept),
               retrieval_id=retrieval['retrieval_id'] if retrieval else None,
               context_hits=kept,decisions=decisions,**package,request=request,
               routing_id=routing['routing_id'] if routing else None,
               routing_decision=routing['decision'] if routing else None,
               routing_generation_seconds=routing['generation_seconds'] if routing else 0)
    # Durably save the exact request and retrieval printout BEFORE invoking the generator.
    row['request_saved_at'] = now()
    append_json(out/'requests.jsonl',row)
    if config_name != 'A':
        print_retrieval(q['id'],k,hits,transcript)
        print_retrieval(q['id'],k,hits,sys.stdout)
    transcript.write(f"\n{now()} GENERATION START {response_id}\nPROMPT\n{package['prompt']}\n")
    transcript.flush()
    print(f"{now()} GENERATION START {response_id}",flush=True)
    row['generation_started_at'] = now()
    t=time.perf_counter()
    try:
        raw = generator.generate(request)
        row.update(raw_response=raw,answer=raw.get('response',''),error=None,
                   status='complete' if raw.get('done') and raw.get('done_reason')=='stop' else 'incomplete')
        row['actual_prompt_fits_reserved_window'] = raw.get('prompt_eval_count',0)+config['options']['num_predict'] <= config['options']['num_ctx']
        row['token_counter_with_margin_bounds_actual'] = raw.get('prompt_eval_count',0) <= package['prompt_token_bound']+128
    except Exception as exc:
        row.update(raw_response=None,answer=None,error=f'{type(exc).__name__}: {exc}',status='failed')
    row['generation_seconds']=time.perf_counter()-t
    row['finished_at']=now()
    row['query_embedding_seconds']=retrieval['query_embedding_seconds'] if retrieval else 0
    row['retrieval_seconds']=retrieval['retrieval_seconds'] if retrieval else 0
    row['end_to_end_seconds']=time.perf_counter()-started+row['query_embedding_seconds']+row['retrieval_seconds']
    row['timing_note']='Input construction + generation + recorded retrieval timings; B/C share the measured retrieval, index construction excluded.'
    append_json(out/'responses.jsonl',row)
    transcript.write(f"{now()} GENERATION END {response_id} {row['status']}\n{row['answer'] if row['answer'] is not None else row['error']}\n")
    transcript.flush()
    print(f"{response_id} {row['status']}: {row['answer'] if row['answer'] is not None else row['error']}",flush=True)
    return row


def snapshot(config, out):
    frozen=out/'frozen'; frozen.mkdir()
    paths=[INPUTS/'CORPUS_MANIFEST.json',INPUTS/'questions.yaml',INPUTS/'development_questions.yaml',
           INPUTS/'source_audit.json',ROOT/'requirements-rag.txt',ROOT/'code/rag.py',
           ROOT/'src/retrieval/embedding.py',ROOT/'src/retrieval/indexing.py',
           *[ROOT/'src/rag'/name for name in ('__init__.py','pipeline.py','runner.py','hybrid.py')]]
    manifest=read_yaml(INPUTS/'CORPUS_MANIFEST.json')
    for source in manifest['sources']:
        paths.extend([ROOT/source['path'],ROOT/source.get('page_map',source.get('section_map'))])
    paths.extend([INPUTS/'calibration.json',ROOT/config.get('model_assets_path','reports/hw04/raw/part4/setup/model_assets.json'),
                  ROOT/'reports/hw04/raw/part4/setup/environment.json'])
    if config.get('generator_tokenizer'):
        paths.append(ROOT/config.get('generator_tokenizer_record','reports/hw04/raw/part4/setup/generator-tokenizer.json'))
    records={}
    for p in paths:
        rel=p.relative_to(ROOT)
        dest=frozen/rel; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,dest)
        records[str(rel)]=digest(p)
    write_json(frozen/'experiment_config.json',config)
    records['experiment_config.json']=digest(frozen/'experiment_config.json')
    return records


def generation_counter(config):
    if not config.get('generator_tokenizer'):
        return token_bound
    from huggingface_hub import snapshot_download
    from tokenizers import Tokenizer
    spec=config['generator_tokenizer']
    cache=Path(spec['cache'])
    if not cache.is_absolute(): cache=ROOT/cache
    local=snapshot_download(spec['model'],revision=spec['revision'],cache_dir=str(cache),
                            local_files_only=True,allow_patterns=['tokenizer.json'])
    tokenizer=Tokenizer.from_file(str(Path(local)/'tokenizer.json'))
    return lambda text:len(tokenizer.encode(text,add_special_tokens=False).ids)


def execute(mode, output, config_path=None, embedding_cache=None):
    config=read_yaml(config_path or INPUTS/'experiment_config.yaml')
    validate_config(config)
    if embedding_cache:
        config['embedding_cache']=str(Path(embedding_cache).resolve())
    if mode=='run' and config.get('calibration_status')!='frozen':
        raise ValueError('Freeze development calibration before scored generation')
    out=Path(output).resolve(); out.mkdir(parents=True,exist_ok=False)
    metadata=dict(started_at=now(),mode=mode,command=sys.argv,python=sys.version,platform=platform.platform(),
       commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
       dirty_state=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),config=config,
       code_and_input_hashes=snapshot(config,out))
    write_json(out/'run_metadata.json',metadata)
    try:
        frozen_inputs=out/'frozen/reports/hw04/part4'
        manifest=read_yaml(frozen_inputs/'CORPUS_MANIFEST.json')
        questions=validate_questions(read_yaml(frozen_inputs/'questions.yaml'))
        dev=read_yaml(frozen_inputs/'development_questions.yaml')['questions']
        embed,index,chunks,audit=build_corpus(config,manifest,out,out/'frozen')
        write_json(out/'gold_chunk_audit.json',gold_audit(questions,chunks))
        lookup={c['chunk_id']:c for c in chunks}
        selected=dev if mode in ('inspect','pilot') else questions
        retrievals={}
        for q in selected:
            ks=[5] if mode=='inspect' else ([1,3,5] if q['id']=='Q2' and mode=='run' else [3])
            for k in ks:
                hits,timings=retrieve(q['question'],k,embed,index,lookup,config.get('retrieval_method','dense'))
                r=dict(retrieval_id=f"{q['id']}-k{k}",question_id=q['id'],question=q['question'],requested_k=k,
                   returned_count=len(hits),retrieved_at=now(),hits=hits,**timings,
                   evidence_coverage=evidence_coverage(q,hits),index_fingerprint=audit['fingerprint'])
                retrievals[(q['id'],k)]=r
                append_json(out/'retrievals.jsonl',r)
                with (out/'retrieved_chunks.txt').open('a') as stream:
                    print_retrieval(q['id'],k,hits,stream)
                if mode=='inspect':
                    print_retrieval(q['id'],k,hits,sys.stdout)
        if mode != 'inspect':
            token_counter=generation_counter(config)
            generator=Ollama(config)
            metadata['generator_identity']=generator.identity
            metadata['ollama_version']=generator.version
            write_json(out/'run_metadata.json',metadata)
            try:
                with (out/'RUN_LOG.txt').open('w') as transcript:
                    for q in selected:
                        for c in (('C',) if mode=='pilot' else ('A','B','C')):
                            measured_answer(q,c,0 if c=='A' else 3,retrievals.get((q['id'],3)),config,out,generator,
                                            'development' if mode=='pilot' else 'main',transcript,token_counter)
                    if mode=='run':
                        q=next(q for q in questions if q['id']=='Q2')
                        for k in (1,5):
                            for c in ('B','C'):
                                measured_answer(q,c,k,retrievals[(q['id'],k)],config,out,generator,'sweep',transcript,token_counter)
                        write_json(out/'sweep_references.json',[
                            dict(question_id='Q2',configuration=c,k=k,response_id=f'Q2-{c}-k{k}',
                                 reused_main=(k==3)) for c in ('B','C') for k in (1,3,5)])
            finally:
                generator.close()
        metadata['finished_at']=now(); metadata['status']='recorded'
        metadata['index_fingerprint']=audit['fingerprint']
        metadata['live_input_changes_during_run']=[p for p,h in metadata['code_and_input_hashes'].items()
            if p!='experiment_config.json' and (not (ROOT/p).exists() or digest(ROOT/p)!=h)]
        if metadata['live_input_changes_during_run']:
            raise ValueError('Live code/inputs changed during run; frozen evidence preserved, select a new run')
    except Exception as exc:
        metadata.update(finished_at=now(),status='failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        write_json(out/'run_metadata.json',metadata)
        write_json(out/'evidence_hashes.json',{str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*'))
                        if p.is_file() and p.name!='evidence_hashes.json'})
    return out

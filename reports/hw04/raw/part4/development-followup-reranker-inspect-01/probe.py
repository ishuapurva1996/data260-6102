import json,sys,time,shutil
from pathlib import Path
import torch
from transformers import AutoTokenizer,AutoModelForSequenceClassification
root=Path.cwd(); sys.path.insert(0,str(root))
from src.rag.runner import evidence_coverage
setup=root/'reports/hw04/raw/part4/followup-setup-20260928'
assets=json.loads((setup/'reranker-assets.json').read_text())
src=root/'reports/hw04/raw/part4/development-followup-hybrid-inspect-01'
out=root/'reports/hw04/raw/part4/development-followup-reranker-inspect-01'; out.mkdir(exist_ok=False)
shutil.copyfile(__file__,out/'probe.py'); (out/'model_assets.json').write_text(json.dumps(assets,indent=2))
torch.set_num_threads(1); tokenizer=AutoTokenizer.from_pretrained(assets['snapshot'],local_files_only=True)
model=AutoModelForSequenceClassification.from_pretrained(assets['snapshot'],local_files_only=True).eval()
chunks={r['chunk_id']:r for r in map(json.loads,(src/'chunks.jsonl').read_text().splitlines())}
qs={q['id']:q for q in json.loads((root/'reports/hw04/part4/development_questions.yaml').read_text())['questions']}
for r in map(json.loads,(src/'retrievals.jsonl').read_text().splitlines()):
 hits=[dict(chunks[h['chunk_id']],**h) for h in r['ranking_audit'][:20]]
 t=time.perf_counter(); pairs=[(r['question'],h['text']) for h in hits]
 token_counts=[len(tokenizer(q,p,add_special_tokens=True,truncation=False)['input_ids']) for q,p in pairs]
 assert max(token_counts)<=512
 features=tokenizer([q for q,p in pairs],[p for q,p in pairs],padding=True,truncation=False,return_tensors='pt')
 with torch.no_grad(): scores=model(**features).logits.flatten().tolist()
 for h,s,nt in zip(hits,scores,token_counts): h.update(reranker_score=s,reranker_pair_tokens=nt)
 hits.sort(key=lambda h:(-h['reranker_score'],h['source_id'],h['start']))
 for rank,h in enumerate(hits,1): h['reranker_rank']=rank
 row=dict(question_id=r['question_id'],question=r['question'],candidate_pool=20,hits=hits,seconds=time.perf_counter()-t,top3_coverage=evidence_coverage(qs[r['question_id']],hits[:3]))
 with (out/'retrievals.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 print(r['question_id'],row['top3_coverage'],[(h['chunk_id'],round(h['reranker_score'],3)) for h in hits[:3]],flush=True)

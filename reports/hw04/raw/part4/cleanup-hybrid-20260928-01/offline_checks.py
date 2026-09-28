"""Cleanup checks only: synthetic fixtures, file copying/hashes, no model calls."""
import hashlib, importlib.util, json, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT))
from src.rag import runner
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
setup=Path(__file__).resolve().parent
pre=read(setup/'preflight.json')
run=ROOT/'reports/hw04/raw/part4/scored-20260928-04'
config=read(ROOT/'reports/hw04/part4/experiment_config.yaml')
checks={}
checks['historical_files_unchanged']=all((ROOT/p).is_file() and sha(ROOT/p)==h for p,h in pre['historical_file_hashes'].items())
checks['protected_configuration_scoring_and_parts123_unchanged']=all(sha(ROOT/p)==h for p,h in pre['protected_file_hashes'].items())
archive=read(ROOT/pre['archive_manifest'])
checks['exact_archive_matches']=all(sha(ROOT/e['archive_path'])==e['sha256'] and (ROOT/e['archive_path']).stat().st_size==e['bytes'] for e in archive['entries'])
checks['live_helper_and_dedicated_tests_removed']=all(not (ROOT/e['former_live_path']).exists() for e in archive['entries'])
spec=importlib.util.spec_from_file_location('pre_cleanup_runner',run/'frozen/src/rag/runner.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
lookup={str(i):dict(chunk_id=str(i),source_id='fixture',start=i,text='Synthetic passage') for i in range(5)}
class Index:
    def as_retriever(self, similarity_top_k):
        self.k=similarity_top_k
        return self
    def retrieve(self, bundle):
        assert bundle.query_str=='Synthetic question' and bundle.embedding==[.1,.2,.3]
        return [SimpleNamespace(node=SimpleNamespace(node_id=str(i)),score=.9-i/10) for i in reversed(range(self.k))]
embed=SimpleNamespace(_model=SimpleNamespace(tokenizer=SimpleNamespace(encode=lambda *a,**kw:[1,2])),get_query_embedding=lambda question:[.1,.2,.3])
for k in (1,3,5):
    before=old.retrieve('Synthetic question',k,embed,Index(),lookup,'dense')
    after=runner.retrieve('Synthetic question',k,embed,Index(),lookup,'dense')
    assert before[0]==after[0]
    assert set(before[1])==set(after[1])
    assert before[1]['retrieval_method']==after[1]['retrieval_method']=='dense'
    assert before[1]['ranking_audit']==after[1]['ranking_audit']==[]
checks['dense_top_k_order_scores_metadata_fixture_parity']=True
try:
    runner.retrieve('Synthetic question',3,embed,Index(),lookup,'hybrid_rrf')
except ValueError as exc:
    checks['retired_method_rejected']=str(exc)=='Unknown retrieval method'
else:checks['retired_method_rejected']=False
with tempfile.TemporaryDirectory(prefix='hw4-dense-snapshot-') as temp:
    records=runner.snapshot(config,Path(temp))
    checks['snapshot_without_hybrid_dependency']='src/rag/hybrid.py' not in records and records['src/rag/runner.py']==sha(ROOT/'src/rag/runner.py')
report=ROOT/'reports/hw04/part4/REPORT_SECTION.md'
analysis=lambda text:text.split('<!-- ANALYSIS_START -->')[1].split('<!-- ANALYSIS_END -->')[0]
checks['analysis_unchanged']=analysis(report.read_text())==analysis((setup/'before/reports/hw04/part4/REPORT_SECTION.md').read_text())
python_files=['code/rag.py','src/rag/pipeline.py','src/rag/runner.py','src/rag/evaluation.py','scripts/verify_hw04_part4.py','reports/hw04/part4/experiments/render_followup_report.py']
subprocess.run([sys.executable,'-m','py_compile',*python_files],cwd=ROOT,check=True)
checks['python_compilation']=True
subprocess.run(['/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node','--check','scripts/capture_hw04_part4.cjs'],cwd=ROOT,check=True)
checks['capture_script_syntax']=True
checks['head_branch_staging_unchanged']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==pre['head'] and subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()==pre['branch'] and subprocess.check_output(['git','diff','--cached'],cwd=ROOT,text=True)==pre['staged_diff']
receipt={'at':datetime.now(timezone.utc).isoformat(),'selected_run':run.name,'scope':'Optional rejected-hybrid cleanup; no model experiments or semantic rescoring','model_calls':0,'database_calls':0,'historical_files_checked':len(pre['historical_file_hashes']),'selected_run_files_checked':sum(p.startswith('reports/hw04/raw/part4/scored-20260928-04/') for p in pre['historical_file_hashes']),'selected_capture_files_checked':sum(p.startswith('reports/hw04/screenshots/part4/scored-20260928-04/') for p in pre['historical_file_hashes']),'checks':checks,'passed':sum(checks.values()),'total':len(checks),'limitations':['Dense parity uses explicit synthetic embeddings/index responses, not a model or new real retrieval experiment.','Historical semantic judgments are unchanged; these checks do not independently establish answer quality.']}
output=Path(sys.argv[1]) if len(sys.argv)>1 else setup/'checks.json'
with output.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps(receipt,indent=2))
assert all(checks.values())

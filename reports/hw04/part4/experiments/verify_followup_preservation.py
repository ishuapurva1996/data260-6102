"""Read-only preservation audit; write a receipt for the local follow-up."""
import hashlib,json,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[4]
setup=ROOT/'reports/hw04/raw/part4/followup-setup-20260928'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
git=lambda *args:subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
pre=read(setup/'preflight.json'); shared=['reports/hw04/AI_USE.md','reports/hw04/METRICS.md','reports/hw04/RUN_LOG.txt']
changed=git('diff','--name-only','HEAD').splitlines()
historical_changes=[p for p,h in pre['historical_file_hashes'].items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
prefixes=[]
for p in shared:
 old=(setup/'before'/p).read_bytes();current=(ROOT/p).read_bytes()
 prefixes.append(dict(path=p,prior_sha256=hashlib.sha256(old).hexdigest(),current_sha256=hashlib.sha256(current).hexdigest(),prior_bytes=len(old),current_bytes=len(current),exact_prior_prefix=current.startswith(old)))
receipt=ROOT/'reports/hw04/verification.parts123.json'; old_receipt=subprocess.check_output(['git','show','HEAD:reports/hw04/verification.parts123.json'],cwd=ROOT)
run=ROOT/'reports/hw04/raw/part4/scored-20260928-04'; screenshot=ROOT/'reports/hw04/screenshots/part4/scored-20260928-04/manifest.json'; captures=read(screenshot)['captures']
report=ROOT/'reports/hw04/part4/REPORT_SECTION.md';reporttext=report.read_text()
responses=[json.loads(line) for line in (run/'responses.jsonl').read_text().splitlines()]
missing=[]
for p in [report,ROOT/'reports/hw04/part4/HANDOFF.md',ROOT/'reports/hw04/part4/FOLLOWUP_DIAGNOSIS.md']:
 for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  link=unquote(link.strip('<>')).split('#')[0]
  if link and not re.match(r'^[a-z]+:',link) and not (p.parent/link).resolve().exists():missing.append(dict(file=str(p.relative_to(ROOT)),target=link))
png_failures=[]
for c in captures:
 for field,hfield in [('path','sha256'),('html_path','html_sha256')]:
  if sha(ROOT/c[field])!=c[hfield]:png_failures.append(c[field])
checks={'head_unchanged':git('rev-parse','HEAD')==pre['head'],'branch_unchanged':git('branch','--show-current')=='codex/hw4-part2-backend','nothing_staged':not git('diff','--cached','--name-only'),'only_shared_reports_modified_among_tracked_files':set(changed)==set(shared),'all_other_tracked_application_and_historical_files_unchanged':set(changed)<=set(shared),'all_prior_shared_content_preserved':all(p['exact_prior_prefix'] for p in prefixes),'all_469_historical_raw_and_screenshot_files_unchanged':len(pre['historical_file_hashes'])==469 and not historical_changes,'parts123_receipt_byte_identical_to_HEAD':receipt.read_bytes()==old_receipt,'all_22_raw_answer_blocks_in_report':all(f"```text\n{r['answer']}\n```" in reporttext for r in responses),'report_and_handoff_local_links_exist':not missing,'all_25_png_and_html_hashes_match':len(captures)==25 and not png_failures,'report_reproduction_byte_identical':report.read_bytes()==Path('/tmp/hw04-part4-report-review.md').read_bytes(),'owned_service_stopped':not read(setup/'service_cleanup.json')['listener_remaining']}
out=dict(audited_at=datetime.now(timezone.utc).isoformat(),selected_run=run.name,checks=checks,passed=sum(checks.values()),total=len(checks),historical_file_count=len(pre['historical_file_hashes']),historical_changes=historical_changes,tracked_changes=changed,shared_prefix_checks=prefixes,missing_links=missing,screenshot_hash_failures=png_failures,scope_notes=['Git diff establishes unchanged tracked application/evidence files except the three append-only shared reports.','Historical raw/screenshot hashes are compared to the follow-up entry inventory.','No database commands or connections occurred; this is not a new database snapshot or benchmark.','Parts1–3 saved46/46 verification remains historical, not rerun.'])
(ROOT/'reports/hw04/part4/preservation_audit.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2));assert all(checks.values())

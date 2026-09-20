"""Recreate counted UTF-8 snapshots from the four archived federal PDFs.

Requires Poppler pdftotext. No download, embedding, or retrieval is performed.
Only text/*.txt files listed in CORPUS_MANIFEST.json are corpus inputs.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import unicodedata

ROOT = Path(__file__).resolve().parent
SELECTIONS = {
    'hud_tenant_selection': list(range(1, 68)),
    'hud_income_rent': list(range(1, 82)),
    'epa_lead_2026': list(range(2, 17)),
    'hud_fair_housing': list(range(5, 11)) + list(range(14, 20)),
}

def clean_page(page, name, number):
    if name == 'hud_fair_housing' and number == 14:
        page = page[page.index('If You Are Disabled:'):]
    if name == 'hud_fair_housing' and number == 10:
        page = page[:page.index('For Connecticut,')]
    lines = page.splitlines()
    kept = []
    for position, line in enumerate(lines):
        if name == 'epa_lead_2026' and position >= len(lines)-4:
            line = re.sub(r'\s{5,}\d+\s*$', '', line)
            line = re.sub(r'^\d+\s{5,}', '', line)
        text = unicodedata.normalize('NFKC', line).strip()
        if not text:
            kept.append('')
            continue
        if name.startswith('hud_') and name != 'hud_fair_housing':
            if '4350.3 REV-1' in text or text.startswith('HUD Occupancy Handbook'):
                continue
            if text.startswith('Chapter 4: Waiting List') or text.startswith('Chapter 5: Determining Income'):
                continue
            if position < 4 and text in {
                'Tenant Selection Plan', 'Marketing', 'Waiting List Management',
                'Selecting Tenants from the Waiting List', 'Determining Annual Income',
                'Determining Adjusted Income', 'Verification', 'Calculating Tenant Rent',
            }:
                continue
        if name == 'hud_fair_housing' and text == 'FAIR HOUSING Equal Opportunity for All':
            continue
        if name in {'epa_lead_2026', 'hud_fair_housing'} and re.fullmatch(r'\d+|[ivx]+', text):
            continue
        text = text.replace('\uf0b7', '•').replace('\x02', '-').replace('\u00ad', '')
        kept.append(re.sub(r'\s+', ' ', text))
    # PDF soft line wrapping is flattened within paragraphs; page boundaries remain.
    paragraphs = []
    for block in re.split(r'\n\s*\n', '\n'.join(kept)):
        if block.strip():
            block = re.sub(r'-\n(?=\w)', '-', block.strip())
            paragraphs.append(' '.join(block.splitlines()))
    return '\n\n'.join(paragraphs).strip()

def main():
    (ROOT/'text').mkdir(exist_ok=True)
    page_map = {}
    for name, selected in SELECTIONS.items():
        raw = subprocess.check_output(['pdftotext', '-layout', str(ROOT/'originals'/f'{name}.pdf'), '-']).decode('utf-8')
        pages = raw.split('\f')
        chunks = []
        records = []
        offset = 0
        seen_paragraphs = set()
        duplicate_paragraphs_removed = 0
        for number in selected:
            page = clean_page(pages[number-1], name, number)
            unique = []
            for paragraph in page.split('\n\n'):
                if len(paragraph) > 100 and paragraph in seen_paragraphs:
                    duplicate_paragraphs_removed += 1
                    continue
                seen_paragraphs.add(paragraph)
                unique.append(paragraph)
            page = '\n\n'.join(unique)
            if not page:
                continue
            block = page + '\n\n'
            records.append({'pdf_page_1based':number,'start_character':offset,'end_character':offset+len(page)})
            chunks.append(block)
            offset += len(block)
        result = ''.join(chunks).rstrip()+'\n'
        out=ROOT/'text'/f'{name}.txt'
        out.write_text(result,encoding='utf-8')
        data=out.read_bytes()
        page_map[name] = {'text_sha256':hashlib.sha256(data).hexdigest(),'duplicate_substantive_paragraphs_removed':duplicate_paragraphs_removed,'pages':records}
        print(f'{name}: {len(data):,} UTF-8 bytes; {len(records)} substantive PDF pages')
    (ROOT/'page_map.json').write_text(json.dumps(page_map,indent=2)+'\n')

if __name__ == '__main__':
    main()

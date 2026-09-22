#!/usr/bin/env python3
"""Display the complete Q2 token result from the saved retrieval rerun."""
from pathlib import Path
import json
import textwrap
import yaml

root = Path(__file__).resolve().parents[1] / 'worktrees' / 'integration'
run = root / 'reports/hw03/raw/part2/manual-screenshots-20260921'
records = json.loads((run / 'records.json').read_text())
questions = yaml.safe_load((root / 'reports/hw03/questions.yaml').read_text())['questions']
record = next(r for r in records if r['question_id'] == 'Q2' and r['technique'] == 'token')
question = next(q for q in questions if q['id'] == 'Q2')
hit = next(h for h in record['hits'] if h['store_rank'] == 1)
assert record['question'] == question['question']
assert len(hit['retrieved_text']) == hit['character_length']

def paragraph(text):
    print(textwrap.fill(text, width=110, break_long_words=False, break_on_hyphens=False))

print('Q2 | Token chunking | Rank 1')
paragraph('Question: ' + record['question'])
print()
paragraph('Expected answer: ' + question['expected_answer'])
print()
print(f"Store score: {hit['store_score']:.6f} | Cosine similarity: {hit['cosine']:.6f}")
print(f"Source: {hit['source_id']} | Complete returned chunk: {hit['character_length']} characters")
print('-' * 110)
for text in hit['retrieved_text'].split('\n'):
    paragraph(text)
print('-' * 110)

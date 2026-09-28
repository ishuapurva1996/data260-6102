#!/usr/bin/env python3
"""Reproduce the frozen EPA article text and half-open character section map.

No HTTP requests. The retained HTML is the sole input. Only the publication's
main article is kept; navigation, language links and promotional resource box
are excluded. Headings, substantive paragraphs/list items, and final resource
list are kept. Inline links retain visible text. NFKC and whitespace cleanup
match the inherited corpus conventions; no substantive wording is rewritten.
"""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / 'originals/epa_disclosure_2026.html'
TEXT = HERE / 'text/epa_disclosure_2026.txt'
SECTION_MAP = HERE / 'section_map.json'
TITLE = 'Real Estate Disclosures about Potential Lead Hazards'
INTRO = 'Information for homebuyers, renters, property managers, landlords, real estate agents and home sellers.'

class MainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'ul', 'ol', 'br'}:
            self.parts.append('\n\n')
    def handle_endtag(self, tag):
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'ul', 'ol'}:
            self.parts.append('\n\n')
    def handle_data(self, data):
        self.parts.append(data)


def main():
    original = ORIGINAL.read_text(encoding='utf-8')
    start = original.index('<p><span>Though lead-based paint for use in homes')
    stop = original.index('</article>', start)
    parser = MainText()
    parser.feed(original[start:stop])
    normalized = unicodedata.normalize('NFKC', ''.join(parser.parts))
    blocks = [re.sub(r'\s+', ' ', s).strip() for s in normalized.split('\n\n')]
    text = '\n\n'.join([TITLE, INTRO] + [b for b in blocks if b]) + '\n'
    TEXT.write_text(text, encoding='utf-8')
    headings = [TITLE, 'Requirements Under the Disclosure Rule',
                'What Happens if a Seller or Lessor Fails to Comply with These Regulations',
                'For More Information']
    locations = [text.index(h) for h in headings]
    sections = [{'title':h, 'start_character':s, 'end_character':locations[i+1] if i+1 < len(locations) else len(text)}
                for i, (h, s) in enumerate(zip(headings, locations))]
    data = {'schema_version':1, 'source_id':'EPA_DISCLOSURE',
            'offset_units':'Python Unicode characters; zero-based half-open [start,end)',
            'text_sha256':hashlib.sha256(TEXT.read_bytes()).hexdigest(),
            'original_sha256':hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),
            'sections':sections}
    SECTION_MAP.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({'characters':len(text),'bytes':len(TEXT.read_bytes()),'sections':len(sections),'sha256':data['text_sha256']}))

if __name__ == '__main__':
    main()

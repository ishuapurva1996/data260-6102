"""Synthetic original fixture and independently predeclared conflict outcomes."""
from pathlib import Path
import json


def original_memory() -> str:
    lines = ['<!-- last_consolidated_utc: 2026-10-19T06:00:00+00:00 -->',
             '- [F01] budget: 2200 USD',
             '- [F02] budget: 2400 USD | corrects=F01',
             '- [F03] move_in: 2026-11-01',
             '- [F04] move_in: 2026-12-01 | corrects=F03',
             '- [F05] parking: required',
             '- [F06] parking: unnecessary']
    for first, key, value in [(7, 'neighborhood', 'Willow Glen'), (17, 'pet', 'one cat'),
                              (27, 'access', 'step-free entry')]:
        lines.extend(f'- [F{i:02d}] {key}: {value}' for i in range(first, first+10))
    facts = [('bedrooms','two'), ('lease','12 months'), ('smoking','non-smoking'),
             ('laundry','in unit'), ('commute','under 30 minutes'), ('tour','Saturday morning'),
             ('contact','email'), ('deposit','at most one month rent'), ('utilities','ask for itemization'),
             ('noise','quiet evenings'), ('floor','ground floor or elevator'), ('bike','secure storage'),
             ('documents','rental application checklist'), ('listing_status','verify before touring'),
             ('transit','near bus stop'), ('workspace','desk space'), ('sunlight','natural light'),
             ('internet','reliable connection')]
    lines.extend(f'- [F{i:02d}] {key}: {value}' for i, (key,value) in enumerate(facts,37))
    assert len(lines) == 55
    return '\n'.join(lines)+'\n'


EXPECTED = {
    'declared_before_consolidation': True,
    'synthetic_fixture': True,
    'original_physical_lines':55, 'original_counted_lines':54,
    'expected_final_physical_lines':28, 'expected_final_counted_lines':27,
    'duplicates':[
        {'ids':[f'F{i:02d}' for i in range(first, first+10)], 'key':key, 'value':value}
        for first,key,value in [(7,'neighborhood','Willow Glen'),(17,'pet','one cat'),
                                 (27,'access','step-free entry')]],
    'conflicts':[
        {'key':'budget','pair':['F01','F02'],'status':'resolved','winner':'F02',
         'reason':'F02 explicitly corrects F01; retain 2200 USD as superseded history.'},
        {'key':'move_in','pair':['F03','F04'],'status':'resolved','winner':'F04',
         'reason':'F04 explicitly corrects F03; retain original date as superseded history.'},
        {'key':'parking','pair':['F05','F06'],'status':'unresolved','winner':None,
         'reason':'Neither claim corrects the other; IDs/order are not recency evidence.'}]
}


def write_original(root: Path) -> None:
    """Explicit fixture setup; never invoked by importing the module or normal CLI."""
    (root/'MEMORY.md').write_text(original_memory())
    evidence = root/'reports/hw06/raw/part4'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence/'MEMORY.original.md').write_text(original_memory())
    (evidence/'expected_conflicts.json').write_text(json.dumps(EXPECTED, indent=2)+'\n')

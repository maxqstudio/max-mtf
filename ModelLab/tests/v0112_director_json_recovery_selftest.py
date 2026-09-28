from __future__ import annotations
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import scientist.core.scientist as scientist
def req(cond,msg):
    if not cond:
        raise AssertionError(msg)

# Exact class of Owner runtime failure: property-name parse error commonly caused by
# a trailing comma before the next closing object/array token.
raw='''{
  "summary": "Generation review",
  "report": {
    "condition": "OK",
    "interpretation": "x",
    "next_action": "y",
    "confidence": 0.8,
  },
  "strategy": {},
  "hypotheses": [],
  "stop_research": false,
}'''
obj=scientist._extract_json(raw)
req(obj['summary']=='Generation review','trailing-comma JSON recovery failed')
req(obj['report']['confidence']==0.8,'nested value changed during recovery')
req(obj['stop_research'] is False,'JSON boolean changed during recovery')

# Python-literal style is also a common harmless serializer defect from LLMs.
raw2="{'summary':'x','report':{'condition':'c','confidence':0.5},'strategy':{},'hypotheses':[],'stop_research':False}"
obj2=scientist._extract_json(raw2)
req(obj2['summary']=='x' and obj2['stop_research'] is False,'safe literal recovery failed')

# Recovery is intentionally bounded: arbitrary unquoted identifiers are not silently
# accepted by the deterministic parser; Director has one explicit format-only LLM retry.
try:
    scientist._extract_json('{summary: "x"}')
except ValueError:
    pass
else:
    raise AssertionError('unquoted identifiers must not be silently normalized locally')

src=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
req('DIRECTOR_GENERATION_REVIEW_JSON_REPAIR' in src or '_JSON_REPAIR' in src,'format-only Director retry missing')
req('Only repair JSON syntax' in src,'format repair prompt must forbid scientific reinterpretation')
req('response_format_recovery' in src,'recovery provenance missing')
print('V0112 DIRECTOR JSON RECOVERY SELFTEST PASS')

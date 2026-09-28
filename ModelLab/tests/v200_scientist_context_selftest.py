from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)
kb=json.loads((ROOT/'scientist/knowledge/SCIENTIST_KNOWLEDGE_BASE.json').read_text(encoding='utf-8'))
p=kb.get('project_mtf') or {}
req(p.get('project')=='Max MTF' and p.get('version')=='2.0.1','Scientist knows Max MTF identity')
req(p.get('strategy_champion') is None and p.get('model_champion') is None,'Scientist knows zero Champion state')
req(p.get('mtf_logic_status')=='MTF1_DATA_FOUNDATION_IMPLEMENTED_NOT_RESEARCH_ACTIVE','Scientist must not claim MTF already implemented')
chat=(ROOT/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8')
req('BASELINE-MTF-V2 is active but is not a Champion' in chat,'Scientist prompt baseline/Champion distinction')
req('never raw C:' in chat,'Scientist prompt terminal-root constraint')
print('V200_SCIENTIST_CONTEXT PASS')

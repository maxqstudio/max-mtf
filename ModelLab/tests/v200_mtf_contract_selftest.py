from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent

def req(x,msg):
    if not x: raise AssertionError(msg)
i=json.loads((PKG/'governance/PROJECT_IDENTITY.json').read_text(encoding='utf-8'))
m=i['mtf_contract']
req(m['TF+2']=='Trend / Regime / Volatility','TF+2 role')
req(m['TF+1']=='Setup / Pullback / Breakout / Structure','TF+1 role')
req(m['TF']=='Primary Decision','TF role')
req(m['TF-1']=='Entry Timing / Execution','TF-1 role')
req(m['example']=={'TF+2':'H4','TF+1':'H1','TF':'M15','TF-1':'M5'},'reference ladder')
road=(ROOT/'docs/mtf/MTF_RESEARCH_ARCHITECTURE_V1_ROADMAP.md').read_text(encoding='utf-8')
req('H4' in road and 'H1' in road and 'M15' in road and 'M5' in road,'roadmap reference ladder')
req('causal' in road.lower() and 'leak' in road.lower(),'roadmap leakage/causal contract')
print('V200_MTF_CONTRACT PASS')

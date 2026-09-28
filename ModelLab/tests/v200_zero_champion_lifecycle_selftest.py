from pathlib import Path
import hashlib,json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from strategy.strategy_challenger_registry import ensure_strategy_registry,SCHEMA

def req(x,msg):
    if not x: raise AssertionError(msg)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

# Acceptance must never mutate packaged runtime authority. Exercise registry
# initialization only inside an isolated sandbox.
production_registry=ROOT/'runtime/strategy_challenger_registry.json'
before=sha(production_registry) if production_registry.exists() else None
with tempfile.TemporaryDirectory() as td:
    app=Path(td)/'ModelLab'; (app/'runtime').mkdir(parents=True,exist_ok=True)
    r=ensure_strategy_registry(app)
    req(r['schema']==SCHEMA,'v2 strategy registry schema')
    req(r.get('current_champion') is None,'Strategy Champion must bootstrap null')
    baseline=r.get('baseline_strategy') or {}
    req(baseline.get('status')=='BASELINE_NOT_CHAMPION','baseline explicit non-Champion')
    req(baseline.get('ea_file')=='EA_v2_00/baseline/Max_MTF.mq5','baseline registry EA identity must be project-relative')
    req(not (r.get('entries') or []),'no inherited Strategy Challengers')
after=sha(production_registry) if production_registry.exists() else None
req(before==after,'zero-Champion acceptance must not mutate packaged runtime registry')

model=json.loads((ROOT/'governance/challenger_registry.json').read_text(encoding='utf-8'))
champ=json.loads((ROOT/'governance/champion_registry.json').read_text(encoding='utf-8'))
req(model.get('entries')==[],'no inherited Model Challengers')
req(champ.get('current') is None and champ.get('history')==[],'Model Champion bootstrap null')
active=json.loads((ROOT/'runtime/active_release.json').read_text(encoding='utf-8'))
req(active['release_id']=='BASELINE-MTF-V2' and active['status']=='BASELINE_NOT_CHAMPION','baseline active release')
req(active['strategy_champion_id'] is None and active['model_champion_id'] is None,'active release has zero Champions')
print('V200_ZERO_CHAMPION_LIFECYCLE PASS')

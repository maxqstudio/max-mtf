from pathlib import Path
import hashlib,json,re,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent; sys.path.insert(0,str(ROOT))
import strategy.strategy_challenger_registry as scr
def req(x,msg):
    if not x: raise AssertionError(msg)

reg=json.loads((ROOT/'runtime/strategy_challenger_registry.json').read_text(encoding='utf-8'))
b=reg.get('baseline_strategy') or {}; path=str(b.get('ea_file') or '')
req(path=='EA_v2_00/baseline/Max_MTF.mq5','packaged baseline registry must use canonical project-relative EA path')
req(not Path(path).is_absolute() and '/mnt/data/' not in path.replace('\\','/'),'packaged baseline registry must not contain builder absolute path')
req(not re.match(r'^[A-Za-z]:[\\/]',path),'packaged baseline registry must not contain Windows absolute project path')
ea=PKG/path; req(ea.is_file(),'portable baseline EA must resolve inside project')
req(hashlib.sha256(ea.read_bytes()).hexdigest()==b.get('ea_sha256'),'portable baseline registry SHA must match canonical EA')
with tempfile.TemporaryDirectory() as td:
    app=Path(td)/'ModelLab'; (app/'runtime').mkdir(parents=True)
    r=scr.ensure_strategy_registry(app); p=str((r.get('baseline_strategy') or {}).get('ea_file') or '')
    req(not Path(p).is_absolute() and '/mnt/data/' not in p.replace('\\','/'),'sandbox initialization must also avoid absolute builder paths')
print('V201_RUNTIME_REGISTRY_PORTABILITY PASS')

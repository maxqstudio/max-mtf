from pathlib import Path
import tempfile,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from host.mt5_installation import validate_mt5_data_root
from core.release_authority import verified_mt5_targets

def req(x,msg):
    if not x: raise AssertionError(msg)
for raw in ('C:\\','C:/','/'):
    try: validate_mt5_data_root(raw)
    except ValueError: pass
    else: raise AssertionError('raw drive/filesystem root must fail closed: '+raw)
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/'ABCDEF0123456789'; (p/'MQL5').mkdir(parents=True)
    r=validate_mt5_data_root(p)
    req(r.verified and r.terminal_id==p.name,'terminal data root verified')
    t=verified_mt5_targets(p)
    req(Path(t['ea_dir']).is_relative_to(p),'EA deploy target under terminal root')
    req(Path(t['model_dir']).is_relative_to(p),'model deploy target under terminal root')
    req(Path(t['tester_profiles_dir']).is_relative_to(p),'Tester target under terminal root')
    req('MaxMTF' in t['ea_dir'] and 'MaxMTF' in t['model_dir'],'Max MTF namespace in terminal')
print('V200_MT5_TERMINAL_ROOT PASS')

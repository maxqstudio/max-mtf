from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent; sys.path.insert(0,str(ROOT))
import core.release_authority as ra
def req(x,msg):
    if not x: raise AssertionError(msg)

obj=json.loads((ROOT/'runtime/active_release.json').read_text(encoding='utf-8'))
ea=PKG/obj['ea']['path']
text=ea.read_text(encoding='utf-8')
m=re.findall(r'^\s*#property\s+version\s+"([^"]+)"',text,flags=re.MULTILINE)
req(len(m)==1,'EA source must expose exactly one version property')
project=json.loads((PKG/'governance/PROJECT_IDENTITY.json').read_text(encoding='utf-8'))
req(obj['ea']['version']==m[0]==project['ea_version'],'active release, EA source, and project EA version must match')
bad=json.loads(json.dumps(obj)); bad['ea']['version']='9.99'
try:
    ra.validate_active_release_record(bad)
    raise AssertionError('forged active release EA version must fail closed')
except ra.ReleaseAuthorityError:
    pass
print('V201_ACTIVE_RELEASE_VERSION_PARITY PASS')

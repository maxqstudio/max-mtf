from pathlib import Path
import hashlib, json, sys
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent; sys.path.insert(0,str(ROOT))
import core.release_authority as ra
def req(x,msg):
    if not x: raise AssertionError(msg)

runtime=json.loads((ROOT/'runtime/active_release.json').read_text(encoding='utf-8'))
package=json.loads((PKG/'Releases/active/release.json').read_text(encoding='utf-8'))
req(runtime==package,'runtime/package active-release mirrors must be exact')
obj=ra.validate_active_release_record(runtime)
ea=PKG/obj['ea']['path']
req(not Path(obj['ea']['path']).is_absolute(),'active release path must be portable relative path')
req(ea.resolve()==(PKG/'EA_v2_00/baseline/Max_MTF.mq5').resolve(),'active release points canonical current EA')
req(obj['ea']['sha256']==hashlib.sha256(ea.read_bytes()).hexdigest(),'stored EA SHA equals actual canonical EA')
req(ra.load_active_release()==obj,'load_active_release validates exact mirrors')

bad=json.loads(json.dumps(obj)); bad['ea']['sha256']='0'*64
try:
    ra.validate_active_release_record(bad)
    raise AssertionError('stale SHA must fail closed')
except ra.ReleaseAuthorityError:
    pass
print('V201_ACTIVE_RELEASE_IDENTITY PASS')

from pathlib import Path
import sys,json,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index,build_lineage_manifest,write_bundle,NATIVE_FRAME_ORDER
from mtf.mtf_data_quality import audit_canonical_bundle
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
views,parity=build_canonical_views(synthetic_native_frames(),price_atol=1e-9)
a,am=build_alignment_index(views)
m=build_lineage_manifest(views,a,symbol='XAUUSD',broker_identity={'server':'TEST'},source_identity={'kind':'SYNTHETIC_TEST'},resampling_parity=parity,alignment_meta=am)
req(m['source_authority']=='M5' and m['forward_fill'] is False and m['future_m5_directional_use'] is False,'manifest authority')
req(set(m['frame_hashes'])==set(NATIVE_FRAME_ORDER),'all four frame hashes')
req(len(m['bundle_identity_sha256'])==64,'bundle hash')
q=audit_canonical_bundle(views,a,parity); req(q['status']=='PASS','bundle DQ pass')
with tempfile.TemporaryDirectory() as td:
    bundle=Path(td)/'bundle'
    r=write_bundle(bundle,views,a,m); req(r['status']=='PASS','bundle write')
    for name in list(NATIVE_FRAME_ORDER)+['alignment','manifest']:
        path=Path(r['files'][name]); req(path.is_file() and path.stat().st_size>0,name+' persisted')
    m2=json.loads(Path(r['files']['manifest']).read_text(encoding='utf-8')); req(m2['bundle_identity_sha256']==m['bundle_identity_sha256'],'manifest identity roundtrip')
print('V201_MTF_LINEAGE_BUNDLE PASS')

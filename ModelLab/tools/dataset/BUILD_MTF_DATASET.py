from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from mtf.mtf_data import (
    build_alignment_index,
    build_canonical_views,
    build_lineage_manifest,
    collect_native_frames_from_mt5,
    write_bundle,
)
from mtf.mtf_data_quality import audit_canonical_bundle
from core.project_paths import MTF_BUNDLES_DIR


def _iso_aware(value: str) -> datetime:
    x=datetime.fromisoformat(value.replace('Z','+00:00'))
    if x.tzinfo is None:
        raise argparse.ArgumentTypeError('timestamp must include timezone offset or Z')
    return x


def main() -> int:
    ap=argparse.ArgumentParser(description='Build a sealed Max MTF M5→M15/H1/H4 canonical dataset bundle from one verified MT5 terminal feed.')
    ap.add_argument('--symbol',required=True)
    ap.add_argument('--from-utc',dest='start_utc',required=True,type=_iso_aware)
    ap.add_argument('--to-utc',dest='end_utc',required=True,type=_iso_aware)
    ap.add_argument('--terminal-exe',default=None)
    ap.add_argument('--out',default=None)
    args=ap.parse_args()
    native,broker=collect_native_frames_from_mt5(symbol=args.symbol,start_utc=args.start_utc,end_utc=args.end_utc,terminal_exe=args.terminal_exe)
    views,parity=build_canonical_views(native,asof_utc=args.end_utc)
    alignment,alignment_meta=build_alignment_index(views)
    source_identity={
        'kind':'DIRECT_MT5_NATIVE_RATES',
        'native_rows':{tf:int(len(df)) for tf,df in native.items()},
        'window':{'from_utc':args.start_utc.isoformat(),'to_utc':args.end_utc.isoformat()},
    }
    dq=audit_canonical_bundle(views,alignment,parity)
    if dq.get('status')!='PASS':
        raise RuntimeError(f'MTF bundle Data Quality failed: {dq}')
    manifest=build_lineage_manifest(
        views,alignment,symbol=args.symbol,broker_identity=broker,source_identity=source_identity,
        resampling_parity=parity,alignment_meta=alignment_meta,data_quality=dq,
    )
    if args.out:
        out=Path(args.out)
    else:
        token=manifest['bundle_identity_sha256'][:12]
        out=MTF_BUNDLES_DIR/f"{args.symbol}_{args.start_utc:%Y%m%d}_{args.end_utc:%Y%m%d}_{token}"
    result=write_bundle(out,views,alignment,manifest)
    # The sealed directory is immutable after atomic commit. Data Quality is
    # identity-bound inside manifest.json; no post-commit file is written into it.
    print(json.dumps({'status':'PASS','bundle':str(out),'identity':manifest['bundle_identity_sha256'],'data_quality':'EMBEDDED_IN_MANIFEST','files':result['files']},indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())

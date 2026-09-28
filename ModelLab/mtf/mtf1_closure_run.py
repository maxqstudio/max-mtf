from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = MODELLAB_ROOT
PKG = ROOT.parent
RUN_FILE = PKG / 'owner_acceptance/runtime/MTF1_CLOSURE_RUN.json'
SCHEMA = 'MAX_MTF1_CLOSURE_RUN_V1'


class ClosureRunError(RuntimeError):
    pass


def _valid_run_id(value: Any) -> bool:
    s = str(value or '')
    return len(s) == 32 and all(c in '0123456789abcdef' for c in s.lower())


def read_run(path: Path = RUN_FILE, *, required: bool = True) -> dict[str, Any] | None:
    p = Path(path)
    if not p.is_file():
        if required:
            raise ClosureRunError(f'CLOSURE_RUN_FILE_MISSING: {p}')
        return None
    try:
        obj = json.loads(p.read_text(encoding='utf-8'))
    except Exception as exc:
        raise ClosureRunError(f'CLOSURE_RUN_FILE_UNREADABLE: {exc}') from exc
    if not isinstance(obj, dict) or obj.get('schema') != SCHEMA or not _valid_run_id(obj.get('closure_run_id')):
        raise ClosureRunError('CLOSURE_RUN_SCHEMA_OR_ID_INVALID')
    try:
        dt = datetime.fromisoformat(str(obj.get('created_utc')).replace('Z', '+00:00'))
    except Exception as exc:
        raise ClosureRunError('CLOSURE_RUN_CREATED_UTC_INVALID') from exc
    if dt.tzinfo is None:
        raise ClosureRunError('CLOSURE_RUN_CREATED_UTC_NAIVE')
    return obj


def start_new_run(path: Path = RUN_FILE) -> dict[str, Any]:
    obj = {
        'schema': SCHEMA,
        'project': 'Max MTF',
        'version': '2.0.1',
        'phase': 'MTF_1_EXTERNAL_EXECUTION_PROOF',
        'closure_run_id': secrets.token_hex(16),
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'authority': 'ONE_SHARED_NONCE_FOR_LOCAL_OWNER_METAEDITOR_FINAL_CLOSURE',
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
    tmp.replace(p)
    return obj


def ensure_run(path: Path = RUN_FILE) -> dict[str, Any]:
    existing = read_run(path, required=False)
    return existing if existing is not None else start_new_run(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--start', action='store_true')
    g.add_argument('--ensure', action='store_true')
    g.add_argument('--show', action='store_true')
    args = ap.parse_args()
    try:
        if args.start:
            obj = start_new_run()
        elif args.ensure:
            obj = ensure_run()
        else:
            obj = read_run(required=True)
        print(json.dumps(obj, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'FAIL', 'reason': str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

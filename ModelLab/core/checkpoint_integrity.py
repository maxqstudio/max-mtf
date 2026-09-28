from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from core.project_paths import PACKAGE_ROOT

SCHEMA = "MAX_CHECKPOINT_FILE_SHA256_V2"
DEFAULT_NAME = "governance/checkpoints/CHECKPOINT_FILE_SHA256.json"
EXCLUDED_NAMES = set()
EXCLUDED_PARTS = {"__pycache__", ".git"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp"}


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(root: Path) -> dict[str,str]:
    root=Path(root).resolve()
    out={}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel=p.relative_to(root)
        rel_s=str(rel).replace("\\","/")
        if rel_s == DEFAULT_NAME or p.name in EXCLUDED_NAMES or any(part in EXCLUDED_PARTS for part in rel.parts) or p.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        out[str(rel).replace("\\","/")]=_sha(p)
    return out


def generate(root: Path, output: Path|None=None) -> dict:
    root=Path(root).resolve(); output=Path(output or (root/DEFAULT_NAME))
    files=inventory(root)
    payload={
        "schema":SCHEMA,
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "root_name":root.name,
        "file_count":len(files),
        "excludes":[DEFAULT_NAME,"__pycache__",".git","*.pyc","*.pyo","*.tmp"],
        "files":files,
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix(output.suffix+".tmp")
    tmp.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")
    tmp.replace(output)
    return payload


def verify(root: Path, manifest: Path|None=None) -> dict:
    root=Path(root).resolve(); manifest=Path(manifest or (root/DEFAULT_NAME))
    try:
        payload=json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status":"FAIL","reason":"MANIFEST_UNREADABLE","error":str(e),"mismatches":[]}
    if payload.get("schema") != SCHEMA:
        return {"status":"FAIL","reason":"SCHEMA_MISMATCH","mismatches":[]}
    expected=payload.get("files") if isinstance(payload.get("files"),dict) else {}
    current=inventory(root)
    mismatches=[]
    for rel in sorted(set(expected)|set(current)):
        if rel not in expected:
            mismatches.append({"path":rel,"kind":"UNMANIFESTED_FILE","actual":current.get(rel)})
        elif rel not in current:
            mismatches.append({"path":rel,"kind":"MISSING_FILE","expected":expected.get(rel)})
        elif expected[rel] != current[rel]:
            mismatches.append({"path":rel,"kind":"HASH_MISMATCH","expected":expected[rel],"actual":current[rel]})
    if int(payload.get("file_count",-1)) != len(expected):
        mismatches.append({"path":"<manifest>","kind":"FILE_COUNT_FIELD_MISMATCH","expected_entries":len(expected),"declared":payload.get("file_count")})
    return {"status":"PASS" if not mismatches else "FAIL","reason":None if not mismatches else "INTEGRITY_MISMATCH","file_count":len(current),"mismatches":mismatches}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default=str(PACKAGE_ROOT))
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--generate",action="store_true")
    g.add_argument("--verify",action="store_true")
    args=ap.parse_args(); root=Path(args.root)
    if args.generate:
        p=generate(root); print(json.dumps({"status":"GENERATED","file_count":p["file_count"],"schema":p["schema"]},indent=2)); return 0
    r=verify(root); print(json.dumps(r,indent=2)); return 0 if r["status"]=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())

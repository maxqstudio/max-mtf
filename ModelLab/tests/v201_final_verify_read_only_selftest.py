from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import mtf.mtf1_final_closure as final
ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / 'acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd'


def req(x, msg):
    if not x:
        raise AssertionError(msg)
    print('PASS ', msg)

text = CMD.read_text(encoding='utf-8', errors='replace')
req('python -m mtf.mtf1_final_closure --verify-existing' in text, 'VERIFY command invokes explicit read-only --verify-existing mode')
req('python -m mtf.mtf1_final_closure\n' not in text.replace('\r\n', '\n'), 'VERIFY command has no generation mode invocation')

with tempfile.TemporaryDirectory() as td:
    p = Path(td) / 'corrupt_final.json'
    p.write_text('{"schema":"CORRUPTED","decision":"MTF_1_CLOSED"}\n', encoding='utf-8')
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    try:
        final.verify_existing_final_closure(p)
        accepted = True
    except Exception:
        accepted = False
    after = hashlib.sha256(p.read_bytes()).hexdigest()
    req(not accepted, 'corrupted existing final evidence remains FAIL')
    req(before == after, 'read-only verifier does not overwrite or repair corrupted evidence')

print('V201_FINAL_VERIFY_READ_ONLY PASS')

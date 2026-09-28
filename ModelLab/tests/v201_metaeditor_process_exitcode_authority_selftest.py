from __future__ import annotations

import inspect
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import acceptance.runners.owner_mtf1_metaeditor_acceptance as meta
from mtf1_closure_test_utils import build_valid_metaeditor_fixture, write_valid_local_acceptance

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
REG = PKG / 'governance/EXTERNAL_RUNTIME_GATES.json'
BASE = PKG / 'owner_acceptance/evidence/mtf1'
BASE.mkdir(parents=True, exist_ok=True)


def req(x, msg):
    if not x:
        raise AssertionError(msg)
    print('PASS ', msg)


def rejected(payload, acc, cfg):
    try:
        meta.verify_metaeditor_evidence_payload(
            payload,
            acceptance_path=acc,
            registry_path=REG,
            config_path=cfg,
            allow_test_fixture=True,
            require_closure_run_id=False,
        )
    except Exception:
        return True
    return False


def synchronized_returncode_fixture(rc: int, *, td: Path, ed: Path, label: str | None = None):
    suffix = label or str(rc).replace('-', 'neg')
    acc = td / f'acceptance_{suffix}.json'
    cfg = td / f'meta_cfg_{suffix}.json'
    write_valid_local_acceptance(acc)
    payload = build_valid_metaeditor_fixture(
        meta,
        acceptance_path=acc,
        config_path=cfg,
        registry_path=REG,
        sandbox=td / f'sandbox_{suffix}',
        artifact_dir=ed / f'art_{suffix}',
    )
    payload['compile']['process_returncode'] = rc
    payload['compile']['returncode_authority'] = meta.RETURNCODE_AUTHORITY
    proc = meta._artifact_from_project_relative(payload['compile']['archived_process_record'])
    pobj = json.loads(proc.read_text(encoding='utf-8'))
    pobj['process_returncode'] = rc
    pobj['returncode_authority'] = meta.RETURNCODE_AUTHORITY
    proc.write_text(json.dumps(pobj, indent=2) + '\n', encoding='utf-8')
    payload['compile']['process_record_sha256'] = meta.sha256_file(proc)
    return payload, acc, cfg


def sync_log(payload, text: str):
    log = meta._artifact_from_project_relative(payload['compile']['archived_log'])
    log.write_text(text, encoding='utf-8')
    parsed = meta._compile_summary(text)
    payload['compile']['compile_log_sha256'] = meta.sha256_file(log)
    payload['compile']['compile_summary'] = parsed
    proc = meta._artifact_from_project_relative(payload['compile']['archived_process_record'])
    pobj = json.loads(proc.read_text(encoding='utf-8'))
    pobj['archived_log_sha256'] = meta.sha256_file(log)
    pobj['compile_summary'] = parsed
    pobj['compile_log_mtime_ns'] = log.stat().st_mtime_ns
    proc.write_text(json.dumps(pobj, indent=2) + '\n', encoding='utf-8')
    payload['compile']['process_record_sha256'] = meta.sha256_file(proc)


def sync_ex5_mtime(payload, mtime_ns: int):
    ex5 = meta._artifact_from_project_relative(payload['compile']['archived_ex5'])
    os.utime(ex5, ns=(mtime_ns, mtime_ns))
    payload['compile']['fresh_ex5']['mtime_ns'] = mtime_ns
    proc = meta._artifact_from_project_relative(payload['compile']['archived_process_record'])
    pobj = json.loads(proc.read_text(encoding='utf-8'))
    pobj['postcompile_ex5_mtime_ns'] = mtime_ns
    proc.write_text(json.dumps(pobj, indent=2) + '\n', encoding='utf-8')
    payload['compile']['process_record_sha256'] = meta.sha256_file(proc)


with tempfile.TemporaryDirectory() as td_raw, tempfile.TemporaryDirectory(dir=BASE) as ed_raw:
    td = Path(td_raw); ed = Path(ed_raw)

    # A: normal zero return code remains valid.
    payload, acc, cfg = synchronized_returncode_fixture(0, td=td, ed=ed, label='case_a')
    meta.verify_metaeditor_evidence_payload(payload, acceptance_path=acc, registry_path=REG, config_path=cfg, allow_test_fixture=True, require_closure_run_id=False)
    req(True, 'CASE A returncode=0 + zero-error log + fresh valid EX5 passes')

    # B: real Owner behavior. Return code is diagnostic evidence only.
    payload, acc, cfg = synchronized_returncode_fixture(1, td=td, ed=ed, label='case_b')
    meta.verify_metaeditor_evidence_payload(payload, acceptance_path=acc, registry_path=REG, config_path=cfg, allow_test_fixture=True, require_closure_run_id=False)
    req(True, 'CASE B returncode=1 + zero-error log + fresh valid EX5 passes')

    # Prove this is not a magic-code-1 exception.
    payload, acc, cfg = synchronized_returncode_fixture(37, td=td, ed=ed, label='diag_37_success')
    meta.verify_metaeditor_evidence_payload(payload, acceptance_path=acc, registry_path=REG, config_path=cfg, allow_test_fixture=True, require_closure_run_id=False)
    req(True, 'arbitrary signed nonzero return code remains diagnostic when semantic compile evidence is valid')

    # C: nonzero diagnostic return code cannot hide a compiler error.
    payload, acc, cfg = synchronized_returncode_fixture(37, td=td, ed=ed, label='case_c')
    source_name = Path(payload['compile']['source_relative_path']).name
    sync_log(payload, f'{source_name} : error 100: test compiler failure\nResult: 1 error, 0 warnings\n')
    req(rejected(payload, acc, cfg), 'CASE C returncode=37 + compiler error fails closed')

    # D: zero-error log cannot compensate for missing EX5.
    payload, acc, cfg = synchronized_returncode_fixture(1, td=td, ed=ed, label='case_d')
    meta._artifact_from_project_relative(payload['compile']['archived_ex5']).unlink()
    req(rejected(payload, acc, cfg), 'CASE D returncode=1 + zero errors + missing EX5 fails closed')

    # E: stale EX5 predating compile window is rejected even with returncode=0.
    payload, acc, cfg = synchronized_returncode_fixture(0, td=td, ed=ed, label='case_e')
    started_ns = int(meta._parse_utc(payload['started_utc'], 'started_utc').timestamp() * 1_000_000_000)
    sync_ex5_mtime(payload, started_ns - 60_000_000_000)
    req(rejected(payload, acc, cfg), 'CASE E stale EX5 predating compile window fails closed')

    # F: return code cannot be rewritten between compile evidence and archived process record.
    payload, acc, cfg = synchronized_returncode_fixture(0, td=td, ed=ed, label='case_f')
    proc = meta._artifact_from_project_relative(payload['compile']['archived_process_record'])
    pobj = json.loads(proc.read_text(encoding='utf-8'))
    pobj['process_returncode'] = 1
    proc.write_text(json.dumps(pobj, indent=2) + '\n', encoding='utf-8')
    payload['compile']['process_record_sha256'] = meta.sha256_file(proc)
    req(rejected(payload, acc, cfg), 'CASE F compile/process-record returncode mismatch fails closed')

    # G: zero-error summary with wrong source identity is not authoritative.
    payload, acc, cfg = synchronized_returncode_fixture(1, td=td, ed=ed, label='case_g')
    sync_log(payload, 'Wrong_Source.mq5 : info\nResult: 0 errors, 0 warnings\n')
    req(rejected(payload, acc, cfg), 'CASE G log/source identity mismatch fails closed')

    # H: tool identity/hash remains independently authoritative.
    payload, acc, cfg = synchronized_returncode_fixture(1, td=td, ed=ed, label='case_h')
    payload['compile']['metaeditor_exe_sha256'] = '0' * 64
    req(rejected(payload, acc, cfg), 'CASE H MetaEditor tool hash mismatch fails closed')

    # Malformed return-code evidence is not coerced.
    payload, acc, cfg = synchronized_returncode_fixture(0, td=td, ed=ed, label='malformed')
    payload['compile']['process_returncode'] = '0'
    req(rejected(payload, acc, cfg), 'string returncode zero is rejected instead of coerced')

# Production generation semantics: execute _run_compile with returncode=1 while the
# real production semantic checker validates a fresh zero-error log + binary EX5.
with tempfile.TemporaryDirectory(dir=BASE) as gen_raw:
    gen = Path(gen_raw)
    gen_acc = gen / 'acceptance.json'
    write_valid_local_acceptance(gen_acc, closure_run_id='1' * 32)
    binding = meta.current_base_candidate_binding(
        acceptance_path=gen_acc,
        registry_path=meta.EXTERNAL_REGISTRY,
        require_fresh_full=True,
        require_closure_run_id=False,
    )
    binding = dict(binding); binding['closure_run_id'] = '1' * 32
    sandbox = gen / 'sandbox'; sandbox.mkdir()
    meta_exe = sandbox / 'MetaEditor64.exe'; meta_exe.write_bytes(b'MZ' + b'X' * 8192)
    data_root = sandbox / 'MT5DATA'; experts = data_root / 'MQL5' / 'Experts'; experts.mkdir(parents=True)
    cfg_path = gen / 'config/config.json'; cfg_path.parent.mkdir(parents=True, exist_ok=True); cfg_path.write_text('{}\n', encoding='utf-8')
    evidence_root = gen / 'artifacts'; evidence = gen / 'OWNER_MTF1_METAEDITOR_ACCEPTANCE.json'

    def fake_subprocess_run(cmd, **kwargs):
        deployed = Path(str(cmd[1]).split(':', 1)[1])
        ex5 = deployed.with_suffix('.ex5'); log = deployed.with_suffix('.log')
        ex5.write_bytes((b'\x00\x9fEX5OWNER' + bytes(range(256))) * 16)
        log.write_text(f'{deployed.name} : info\nResult: 0 errors, 0 warnings\n', encoding='utf-16')
        return SimpleNamespace(returncode=1, stdout='', stderr='')

    tool = {'path': str(meta_exe), 'sha256': meta.sha256_file(meta_exe), 'size_bytes': meta_exe.stat().st_size, 'pe_magic': '4d5a'}
    verified = SimpleNamespace(data_root=str(data_root), terminal_id='TEST_TERMINAL', experts_dir=str(experts))
    with patch.object(meta, 'CONFIG', cfg_path), patch.object(meta, 'EVIDENCE_ROOT', evidence_root), patch.object(meta, 'EVIDENCE', evidence), \
         patch.object(meta, 'current_base_candidate_binding', return_value=binding), \
         patch.object(meta, '_read_config', return_value={'terminal_exe': None, 'metaeditor_exe': str(meta_exe), 'mt5_data_root': str(data_root), 'timeout_seconds': 180}), \
         patch.object(meta, '_resolve_installation', return_value={'terminal': '', 'metaeditor': str(meta_exe), 'data_dir': str(data_root), 'terminal_id': 'TEST_TERMINAL', 'resolution': 'EXPLICIT_CONFIG'}), \
         patch.object(meta, '_validate_metaeditor_binary', return_value=tool), \
         patch.object(meta, 'validate_mt5_data_root', return_value=verified), \
         patch.object(meta.subprocess, 'run', side_effect=fake_subprocess_run), \
         patch.object(meta, 'verify_existing_evidence', return_value={'status': 'PASS'}):
        rc = meta._run_compile()
    generated = json.loads(evidence.read_text(encoding='utf-8'))
    req(rc == 0 and generated['overall_status'] == 'PASS', 'production _run_compile accepts diagnostic returncode=1 when semantic compile authority passes')
    req(generated['compile']['process_returncode'] == 1 and generated['compile']['returncode_authority'] == 'DIAGNOSTIC_ONLY', 'generation preserves exact return code and diagnostic-only authority')

run_src = inspect.getsource(meta._run_compile)
verify_src = inspect.getsource(meta.verify_metaeditor_evidence_payload)
req('_require_zero_process_returncode' not in run_src and '_require_zero_process_returncode' not in verify_src, 'no zero-returncode PASS authority remains in generation or verifier')
req('_assert_compile_semantic_authority' in run_src and '_assert_compile_semantic_authority' in verify_src, 'generation and verifier share semantic log+EX5 compile authority')
req('compile_process_returncode != archived_process_returncode' in verify_src, 'verifier still cross-checks exact return code evidence')

print('V201_METAEDITOR_PROCESS_EXITCODE_AUTHORITY PASS')

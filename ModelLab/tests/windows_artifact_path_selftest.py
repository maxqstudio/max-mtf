from __future__ import annotations

from pathlib import Path
import tempfile

from core.artifact_paths import filesystem_safe_id


def req(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    cases = {
        'hybrid::gru::lightgbm': 'hybrid__gru__lightgbm',
        'hybrid::tcn::lightgbm': 'hybrid__tcn__lightgbm',
        'hybrid::lstm::xgboost': 'hybrid__lstm__xgboost',
        'hybrid::transformer::xgboost': 'hybrid__transformer__xgboost',
        'CON': '_CON',
    }
    invalid = set('<>:"/\\|?*')
    for canonical, expected in cases.items():
        safe = filesystem_safe_id(canonical)
        req(safe == expected, f'{canonical!r} -> {safe!r}, expected {expected!r}')
        req(not any(ch in invalid for ch in safe), f'unsafe Windows filename chars remain: {safe!r}')
        # Canonical identity itself must remain untouched.
        if canonical.startswith('hybrid::'):
            req('::' in canonical, 'selftest accidentally mutated canonical family identity')

    # Validate the exact artifact names that the hybrid exporter will create.
    safe = filesystem_safe_id('hybrid::gru::lightgbm')
    with tempfile.TemporaryDirectory(prefix='cp_windows_path_test_') as td:
        td = Path(td)
        temporal = td / f'{safe}_temporal.onnx'
        policy = td / f'{safe}_policy_model.onnx'
        temporal.write_bytes(b'test')
        policy.write_bytes(b'test')
        req(temporal.exists() and policy.exists(), 'filesystem-safe ONNX artifact paths are not writable')
        req(temporal.name == 'hybrid__gru__lightgbm_temporal.onnx', 'unexpected temporal artifact name')
        req(policy.name == 'hybrid__gru__lightgbm_policy_model.onnx', 'unexpected policy artifact name')

    source = (Path(__file__).resolve().parents[1]/'models/onnx_export.py').read_text(encoding='utf-8')
    req('safe_prefix=filesystem_safe_id(prefix)' in source, 'hybrid exporter does not sanitize at filesystem boundary')
    req("prefix=family" in source, 'preflight must continue passing canonical family ID into exporter')
    print('WINDOWS_ARTIFACT_PATH_SELFTEST_PASS')


if __name__ == '__main__':
    main()

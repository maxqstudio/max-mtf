from __future__ import annotations

import copy
import hashlib
import tempfile
from pathlib import Path

import pandas as pd

import acceptance.runners.owner_mtf1_runtime_acceptance as owner
from mtf1_closure_test_utils import valid_owner_runtime_payload, write_valid_local_acceptance
from mtf_test_utils import synthetic_native_frames

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
REG = PKG / 'governance/EXTERNAL_RUNTIME_GATES.json'
BASE = PKG / 'owner_acceptance/evidence/mtf1'
BASE.mkdir(parents=True, exist_ok=True)


def req(x, msg):
    if not x:
        raise AssertionError(msg)
    print('PASS ', msg)


def rejected(fn):
    try:
        fn()
    except owner.OwnerMTF1AcceptanceError:
        return True
    return False


def mutate_values(frame: pd.DataFrame, row_index: int) -> pd.DataFrame:
    out = frame.copy(deep=True)
    idx = out.index[row_index]
    o = float(out.loc[idx, 'open'])
    c = float(out.loc[idx, 'close']) + 0.07
    out.loc[idx, 'close'] = c
    out.loc[idx, 'high'] = max(float(out.loc[idx, 'high']) + 0.13, o, c)
    out.loc[idx, 'low'] = min(float(out.loc[idx, 'low']) - 0.11, o, c)
    if 'tick_volume' in out.columns:
        out.loc[idx, 'tick_volume'] = int(out.loc[idx, 'tick_volume']) + 17
    if 'spread' in out.columns:
        out.loc[idx, 'spread'] = int(out.loc[idx, 'spread']) + 1
    if 'real_volume' in out.columns:
        out.loc[idx, 'real_volume'] = int(out.loc[idx, 'real_volume']) + 3
    return out


with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory(dir=BASE) as ed:
    td = Path(td); ed = Path(ed)
    acc = td / 'acceptance.json'; cfg = td / 'config/config.json'
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes((PKG / 'owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json').read_bytes())
    write_valid_local_acceptance(acc)

    # Seal inside the last M5 candle so every timeframe has one legitimately
    # mutable native tail row at the original Owner collection instant.
    frames = synthetic_native_frames()
    m5_open = pd.to_datetime(frames['M5']['time'], unit='s', utc=True).max()
    sealed_asof = (m5_open + pd.Timedelta(minutes=2)).to_pydatetime()
    payload = valid_owner_runtime_payload(
        owner,
        acceptance_path=acc,
        config_path=cfg,
        registry_path=REG,
        artifact_dir=ed / 'owner_artifacts',
        frames=frames,
        sealed_asof=sealed_asof,
    )
    owner.verify_owner_evidence_payload(
        payload, acceptance_path=acc, config_path=cfg, registry_path=REG,
        require_live_mt5=False, require_closure_run_id=False,
    )
    req(True, 'archived native inputs replay to exact parity/alignment/DQ/lineage proof')

    minimal = copy.deepcopy(payload); minimal.pop('execution_artifacts', None)
    req(rejected(lambda: owner.verify_owner_evidence_payload(
        minimal, acceptance_path=acc, config_path=cfg, registry_path=REG,
        require_live_mt5=False, require_closure_run_id=False,
    )), 'summary-only Owner PASS without raw execution artifacts rejected')

    archived_frames, _, proof = owner._load_archived_native_inputs(payload)
    broker = dict(payload['broker_provenance'])
    original_raw_sha = {tf: str(proof['native_artifacts'][tf]['sha256']) for tf in owner.NATIVE_TFS}
    original_raw_bytes_sha = {
        tf: hashlib.sha256(owner._artifact_from_project_relative(proof['native_artifacts'][tf]['path']).read_bytes()).hexdigest()
        for tf in owner.NATIVE_TFS
    }

    # 1. M5 live mutation: values of the candle that was still open at the
    # original seal may evolve; its open_time identity may not.
    live_m5_mutation = {tf: df.copy(deep=True) for tf, df in archived_frames.items()}
    live_m5_mutation['M5'] = mutate_values(live_m5_mutation['M5'], -1)
    call_windows = []
    def m5_mutable_probe(**kwargs):
        call_windows.append((kwargs['start_utc'], kwargs['end_utc']))
        return live_m5_mutation, broker
    owner.verify_owner_evidence_payload(
        payload, acceptance_path=acc, config_path=cfg, registry_path=REG,
        require_live_mt5=True, require_closure_run_id=False, live_probe=m5_mutable_probe,
    )
    req(True, 'mutable M5 candle OHLC/volume evolution after seal is accepted')

    # 2. M5 historical mutation must still fail closed.
    live_m5_history = {tf: df.copy(deep=True) for tf, df in archived_frames.items()}
    live_m5_history['M5'] = mutate_values(live_m5_history['M5'], -2)
    def m5_history_probe(**kwargs):
        return live_m5_history, broker
    req(rejected(lambda: owner.verify_owner_evidence_payload(
        payload, acceptance_path=acc, config_path=cfg, registry_path=REG,
        require_live_mt5=True, require_closure_run_id=False, live_probe=m5_history_probe,
    )), 'mutation of fully closed M5 history is rejected')

    # 3. M15/H1/H4 current boundary values may evolve while their exact open
    # timestamps remain fixed.
    live_higher_mutable = {tf: df.copy(deep=True) for tf, df in archived_frames.items()}
    for tf in ('M15', 'H1', 'H4'):
        live_higher_mutable[tf] = mutate_values(live_higher_mutable[tf], -1)
    def higher_mutable_probe(**kwargs):
        return live_higher_mutable, broker
    owner.verify_owner_evidence_payload(
        payload, acceptance_path=acc, config_path=cfg, registry_path=REG,
        require_live_mt5=True, require_closure_run_id=False, live_probe=higher_mutable_probe,
    )
    req(True, 'mutable higher-TF boundary OHLC/volume evolution is accepted')

    # 4. Required boundary open_time removal/change is terminal.
    live_missing_boundary = {tf: df.copy(deep=True) for tf, df in archived_frames.items()}
    live_missing_boundary['H1'] = live_missing_boundary['H1'].iloc[:-1].copy()
    def missing_boundary_probe(**kwargs):
        return live_missing_boundary, broker
    req(rejected(lambda: owner.verify_owner_evidence_payload(
        payload, acceptance_path=acc, config_path=cfg, registry_path=REG,
        require_live_mt5=True, require_closure_run_id=False, live_probe=missing_boundary_probe,
    )), 'required higher-TF boundary timestamp removal is rejected')

    # 5. Closed higher-TF historical data remains immutable.
    live_higher_history = {tf: df.copy(deep=True) for tf, df in archived_frames.items()}
    live_higher_history['M15'] = mutate_values(live_higher_history['M15'], -2)
    def higher_history_probe(**kwargs):
        return live_higher_history, broker
    req(rejected(lambda: owner.verify_owner_evidence_payload(
        payload, acceptance_path=acc, config_path=cfg, registry_path=REG,
        require_live_mt5=True, require_closure_run_id=False, live_probe=higher_history_probe,
    )), 'mutation of fully closed higher-TF native history is rejected')

    # 6. Revalidation must use the ORIGINAL seal/window. A candle that closes
    # later in wall-clock time remains classified by its state at that seal.
    seal = owner._parse_aware_utc(payload['sealed_asof_utc'], 'sealed_asof_utc')
    m5_view = owner._immutable_native_revalidation_view(archived_frames['M5'], 'M5', seal)
    req(m5_view['mutable_tail_rows'] == 1, 'original sealed-asof keeps the then-open M5 candle outside immutable hash')
    req(bool(call_windows) and all(end == seal for _, end in call_windows), 'live refetch reuses original sealed_asof/to_utc instead of recomputing now')

    # 7. Raw archive is never sanitized/rewritten by revalidation.
    for tf in owner.NATIVE_TFS:
        path = owner._artifact_from_project_relative(proof['native_artifacts'][tf]['path'])
        req(hashlib.sha256(path.read_bytes()).hexdigest() == original_raw_bytes_sha[tf] == original_raw_sha[tf], f'{tf} raw archive SHA remains bound to first Owner execution')

    # Evidence exposes immutable-vs-mutable authority per timeframe.
    evidence = payload['immutable_live_revalidation']
    req(evidence['sealed_asof_utc'] == pd.Timestamp(sealed_asof).isoformat(), 'immutable evidence binds original sealed_asof_utc')
    for tf in owner.NATIVE_TFS:
        row = evidence['timeframes'][tf]
        req(row['immutable_revalidation_status'] == 'PASS' and row['immutable_closed_rows'] > 0, f'{tf} immutable closed-bar evidence is explicit')
        req(row['live_immutable_sha256'] == row['immutable_closed_sha256'], f'{tf} live immutable SHA matches archived immutable SHA')
        req(row['mutable_tail_rows'] == 1, f'{tf} mutable tail is explicitly bounded to the row open at seal')
        if tf != 'M5':
            req(bool(row['required_boundary_open_utc']), f'{tf} required mutable boundary open_time is recorded')

    # 8. Existing broker/terminal identity checks remain fail closed.
    bad_broker = dict(broker); bad_broker['server'] = 'DIFFERENT-SERVER'
    def broker_mismatch_probe(**kwargs):
        return archived_frames, bad_broker
    req(rejected(lambda: owner.verify_owner_evidence_payload(
        payload, acceptance_path=acc, config_path=cfg, registry_path=REG,
        require_live_mt5=True, require_closure_run_id=False, live_probe=broker_mismatch_probe,
    )), 'broker/server identity mismatch remains fail closed')

print('V201_OWNER_RAW_REPLAY_AUTHENTICITY PASS')

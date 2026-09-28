from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import mtf.mtf_data as mtf_data
import acceptance.runners.owner_mtf1_runtime_acceptance as owner
from mtf1_closure_test_utils import TEST_RUN_ID, write_valid_local_acceptance
from mtf.mtf1_closure_run import RUN_FILE as CLOSURE_RUN_FILE, SCHEMA as CLOSURE_RUN_SCHEMA
from mtf_test_utils import synthetic_native_frames

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
REG = PKG / 'governance/EXTERNAL_RUNTIME_GATES.json'


def req(value, msg):
    if not value:
        raise AssertionError(msg)
    print('PASS ', msg)


class FakeMT5(types.ModuleType):
    def __init__(self, available):
        super().__init__('MetaTrader5')
        self.available = list(available)
        self.TIMEFRAME_M5 = 5
        self.TIMEFRAME_M15 = 15
        self.TIMEFRAME_H1 = 60
        self.TIMEFRAME_H4 = 240
        self.selected = []
        self.fetches = []
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self.frames = synthetic_native_frames()
        self._tf = {5: 'M5', 15: 'M15', 60: 'H1', 240: 'H4'}

    def initialize(self, *args, **kwargs):
        self.initialize_calls += 1
        return True

    def shutdown(self):
        self.shutdown_calls += 1
        return True

    def last_error(self):
        return (0, 'OK')

    def symbols_get(self):
        return tuple(SimpleNamespace(name=name) for name in self.available)

    def symbol_select(self, symbol, enabled):
        self.selected.append((symbol, bool(enabled)))
        return symbol in self.available

    def copy_rates_range(self, symbol, timeframe, start, end):
        self.fetches.append((symbol, timeframe))
        frame = self.frames[self._tf[timeframe]]
        return frame.to_records(index=False)

    def account_info(self):
        return SimpleNamespace(server='TEST-SERVER', company='TEST-BROKER')

    def terminal_info(self):
        return SimpleNamespace(
            path=r'C:\\Program Files\\MetaTrader 5\\terminal64.exe',
            data_path=r'C:\\Users\\pc\\AppData\\Roaming\\MetaQuotes\\Terminal\\TEST123',
            build=5000,
            name='MetaTrader 5',
        )


@contextmanager
def fake_mt5(available):
    fake = FakeMT5(available)
    old = sys.modules.get('MetaTrader5')
    sys.modules['MetaTrader5'] = fake
    try:
        yield fake
    finally:
        if old is None:
            sys.modules.pop('MetaTrader5', None)
        else:
            sys.modules['MetaTrader5'] = old


def collect(available, *, logical='XAUUSD', override=None):
    start = datetime.now(timezone.utc) - timedelta(days=30)
    end = datetime.now(timezone.utc)
    with fake_mt5(available) as fake:
        frames, broker = mtf_data.collect_native_frames_from_mt5(
            symbol=logical,
            start_utc=start,
            end_utc=end,
            broker_symbol_override=override,
        )
        return frames, broker, list(fake.selected), list(fake.fetches)


# 1. Exact broker symbol wins immediately.
_, broker, selected, fetches = collect(['XAUUSD'])
req(broker['resolved_broker_symbol'] == 'XAUUSD' and broker['symbol_resolution_method'] == 'EXACT', 'exact broker symbol resolves exactly')
req(all(row[0] == 'XAUUSD' for row in fetches) and selected == [('XAUUSD', True)], 'exact resolved symbol used for all four native fetches')

# 2. Actual Owner suffix case.
_, broker, _, fetches = collect(['EURUSD', 'XAUUSD.m', 'GBPUSD'])
req(broker['resolved_broker_symbol'] == 'XAUUSD.m' and broker['symbol_resolution_method'] == 'UNIQUE_SUFFIX_OR_PREFIX', 'Owner XAUUSD.m suffix resolves from logical XAUUSD')
req(all(row[0] == 'XAUUSD.m' for row in fetches), 'XAUUSD.m propagated to every native timeframe fetch')

# 3. Other suffix, no broker-specific suffix list.
_, broker, _, _ = collect(['XAUUSD.a'])
req(broker['resolved_broker_symbol'] == 'XAUUSD.a', 'arbitrary suffix XAUUSD.a resolves without hard-coded suffix list')

# 4. Prefix.
_, broker, _, _ = collect(['m.XAUUSD'])
req(broker['resolved_broker_symbol'] == 'm.XAUUSD', 'prefix broker symbol resolves')

# Exact matching is case-insensitive but preserves broker spelling.
_, broker, _, _ = collect(['xauusd'])
req(broker['resolved_broker_symbol'] == 'xauusd' and broker['symbol_resolution_method'] == 'EXACT', 'exact match is case-insensitive and preserves terminal symbol spelling')

# 5. Ambiguous broker variants must never be guessed.
try:
    collect(['XAUUSD.m', 'XAUUSD.raw'])
except RuntimeError as exc:
    text = str(exc)
    req('explicit broker_symbol_override required' in text and 'XAUUSD.m' in text and 'XAUUSD.raw' in text, 'ambiguous suffix set fails closed and lists candidates')
else:
    raise AssertionError('ambiguous symbol variants were not rejected')

# 6. Explicit override is exact authority.
_, broker, selected, fetches = collect(['XAUUSD.m', 'XAUUSD.raw'], override='XAUUSD.raw')
req(broker['resolved_broker_symbol'] == 'XAUUSD.raw' and broker['symbol_resolution_method'] == 'EXPLICIT_OVERRIDE', 'explicit broker override selects exact requested terminal symbol')
req(selected == [('XAUUSD.raw', True)] and all(row[0] == 'XAUUSD.raw' for row in fetches), 'explicit override propagates to selection and all native fetches')
try:
    collect(['XAUUSD.m'], override='XAUUSD.raw')
except RuntimeError as exc:
    req('explicit broker symbol override unavailable' in str(exc), 'unavailable explicit override fails closed')
else:
    raise AssertionError('missing explicit override was not rejected')

# 7. Missing compatible symbol fails closed.
try:
    collect(['EURUSD', 'GBPUSD', 'XAGUSD'])
except RuntimeError as exc:
    req('logical symbol not found' in str(exc), 'missing logical/broker symbol fails closed')
else:
    raise AssertionError('missing logical symbol was not rejected')

# 8. Exercise the production Owner runtime path end-to-end with XAUUSD.m.
old_test_mode = os.environ.get('MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE')
os.environ['MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE'] = '1'
closure_backup = CLOSURE_RUN_FILE.read_bytes() if CLOSURE_RUN_FILE.exists() else None
CLOSURE_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
CLOSURE_RUN_FILE.write_text(json.dumps({
    'schema': CLOSURE_RUN_SCHEMA,
    'project': 'Max MTF',
    'version': '2.0.1',
    'phase': 'MTF_1_EXTERNAL_EXECUTION_PROOF',
    'closure_run_id': TEST_RUN_ID,
    'created_utc': datetime.now(timezone.utc).isoformat(),
    'authority': 'TEST_PRODUCTION_PATH_SHARED_NONCE',
}, indent=2) + '\n', encoding='utf-8')
try:
    evidence_base = PKG / 'owner_acceptance/evidence/mtf1'
    evidence_base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory(dir=evidence_base) as ad, fake_mt5(['EURUSD', 'XAUUSD.m', 'GBPUSD']) as fake:
        td = Path(td)
        acceptance = td / 'acceptance.json'
        config = td / 'owner_config.json'
        evidence = td / 'OWNER_MTF1_RUNTIME_ACCEPTANCE.json'
        artifacts = Path(ad) / 'owner_runtime'
        config.write_text(json.dumps({
            'schema': 'MAX_MTF1_OWNER_RUNTIME_ACCEPTANCE_CONFIG_V1',
            'symbol': 'XAUUSD',
            'broker_symbol_override': None,
            'lookback_days': 30,
            'terminal_exe': None,
        }, indent=2) + '\n', encoding='utf-8')
        write_valid_local_acceptance(acceptance)

        verified_root = SimpleNamespace(
            terminal_id='TEST123',
            data_root=r'C:\\Users\\pc\\AppData\\Roaming\\MetaQuotes\\Terminal\\TEST123',
        )
        rc = owner._run_owner_runtime(
            acceptance_path=acceptance,
            config_path=config,
            registry_path=REG,
            evidence_path=evidence,
            artifact_root=artifacts,
            collector=mtf_data.collect_native_frames_from_mt5,
            data_root_validator=lambda path: verified_root,
        )
        req(rc == 0, 'production Owner runtime path accepts uniquely resolved XAUUSD.m')
        payload = json.loads(evidence.read_text(encoding='utf-8'))
        req(payload['logical_symbol'] == 'XAUUSD', 'Owner evidence records logical symbol')
        req(payload['symbol'] == payload['resolved_broker_symbol'] == 'XAUUSD.m', 'Owner evidence executable symbol is resolved broker symbol')
        req(payload['symbol_resolution_method'] == 'UNIQUE_SUFFIX_OR_PREFIX' and payload['symbol_resolution_candidates'] == ['XAUUSD.m'], 'Owner evidence records deterministic resolution method and decision candidate set')
        req(payload['broker_provenance']['symbol'] == 'XAUUSD.m', 'broker provenance uses resolved symbol')
        req(payload['lineage_manifest_preview']['symbol'] == 'XAUUSD.m', 'lineage/canonical evidence uses resolved symbol')
        prov_path = PKG / payload['execution_artifacts']['provenance_path']
        if not prov_path.exists():
            # Temporary test artifact paths are project-relative only in normal production;
            # here inspect the actual artifact root directly.
            prov_path = artifacts / payload['candidate_binding']['closure_run_id'] / 'mt5_runtime_provenance.json'
        provenance = json.loads(prov_path.read_text(encoding='utf-8'))
        req(provenance['symbol'] == provenance['resolved_broker_symbol'] == 'XAUUSD.m', 'raw archive provenance uses resolved broker symbol')
        req(all(symbol == 'XAUUSD.m' for symbol, _ in fake.fetches), 'initial fetch and live refetch never revert to logical XAUUSD')
finally:
    if closure_backup is None:
        CLOSURE_RUN_FILE.unlink(missing_ok=True)
    else:
        CLOSURE_RUN_FILE.write_bytes(closure_backup)
    if old_test_mode is None:
        os.environ.pop('MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE', None)
    else:
        os.environ['MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE'] = old_test_mode

print('V201_OWNER_MT5_BROKER_SYMBOL_RESOLUTION PASS')

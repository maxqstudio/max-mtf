from __future__ import annotations

import hashlib
from pathlib import Path

from research.gate_kpi import KPI_UI_HARD_GATE_CONTRACT, default_profiles

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')


def req(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)

# Evaluation formula authority must be byte-identical to v1.4.3. v1.4.4 is a
# transparency/control-surface repair, not a relaxation/rewrite of PASS/FAIL.
EXPECTED={
    'kpi.py':'274ad08001c9050156525661a84f3c26209858d2568010dbf07701b2e7dd66f6',
    'cpcv.py':'4358259d7eed365860d1b6ac331683b1ae168c5385197b67b70e66bb4f508d13',
    'champion_factory.py':'e3487461916baa3375589c9759583e0ce2e64753d3c56f9d869e154dbf5b0732',
    'risk_kpi.py':'c09b2dacea4b06f5aea4dea2588778bf7c437e25fc432c8ef72dd97ec6083b2d',
    'sample_policy.py':'f461061ba21530d5b5fb005e44662ee7332b0d0dea72349ff7266aada33e616e',
}
for name,sha in EXPECTED.items():
    req(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,f'{name} evaluation authority unchanged from v1.4.3')

# Every stage in the canonical hard-gate visibility contract must exist in the
# seeded gate profiles and every editable path must have an operator-visible UI
# binding (generic wildcard risk fields are rendered by shared helpers).
profiles=default_profiles({})
for stage,fields in KPI_UI_HARD_GATE_CONTRACT.items():
    req(stage in profiles,f'{stage} exists in canonical gate profile')
    for field in fields:
        if field.startswith('risk_kpis.*.'):
            leaf=field.split('.')[-1]
            req(leaf in APP,f'{stage} generic risk field {leaf} is exposed in shared UI renderer')
            continue
        if '.' in field:
            parent,leaf=field.split('.',1)
            req(parent in APP and leaf in APP,f'{stage} nested hard gate {field} is exposed in UI')
            continue
        req(f'"{field}"' in APP or f"'{field}'" in APP,f'{stage} hard gate {field} is exposed in UI')

# Explicit regressions for the previously hidden controls.
for token in (
    'Median Recovery','Worst-fold Recovery','Positive months','Positive quarters',
    'Max regime concentration','Max top-10% win share','Spread ×1.25 Min Exp R',
    'Spread ×1.50 Min Exp R','Threshold plateau profitable ratio',
    'Worst Recovery','Every year Exp R ≥ 0','Risk KPI evidence sufficiency · hard when metric is ON',
    'Min active days','Min tail days','Min sample years',
):
    req(token in APP,f'previously hidden KPI/evidence control visible: {token}')

# Inactive Fresh degradation placeholders must not masquerade as active KPI.
req('Fresh degradation placeholders are inactive' in APP,'inactive Fresh degradation fields are disclosed as non-authoritative')

print('V144_KPI_UI_FULL_AUTHORITY_SELFTEST PASS')

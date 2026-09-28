from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from research.gate_kpi import ensure_gate_kpi_profiles, risk_cfg_for_gate
from research.risk_kpi import ensure_risk_kpi_config

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/config.json").read_text(encoding="utf-8"))


def req(cond, msg):
    if not cond:
        raise AssertionError(msg)


# Reproduce the exact legacy sign pattern seen in Owner run evidence.
stale = deepcopy(CFG)
legacy = {
    "discovery": 0.80,
    "cpcv": 1.00,
    "tournament": 1.25,
    "fresh_forward": 1.50,
}
expected = {
    "discovery": -2.00,
    "cpcv": -2.50,
    "tournament": -2.00,
    "fresh_forward": -1.50,
}
for gate, threshold in legacy.items():
    spec = stale["gate_kpis"][gate]["risk_kpis"]["cvar"]
    spec["enabled"] = True
    spec["threshold"] = threshold
    spec["allow_positive_tail_floor"] = False

profiles = ensure_gate_kpi_profiles(stale)
for gate, safe in expected.items():
    cvar = profiles[gate]["risk_kpis"]["cvar"]
    req(abs(float(cvar["threshold"]) - safe) < 1e-12, f"{gate} CVaR legacy sign not migrated to stage-safe floor")
    req(abs(float(cvar.get("migrated_legacy_positive_tail_floor_from")) - legacy[gate]) < 1e-12, f"{gate} legacy CVaR source threshold not preserved")
    req(cvar.get("migration_reason") == "V134_CVAR_SIGN_SEMANTICS_LEGACY_REPAIR", f"{gate} migration provenance missing")
    ensure_risk_kpi_config(risk_cfg_for_gate(stale, gate))

# Explicit positive tail floors remain possible only when Owner acknowledges semantics.
explicit = deepcopy(CFG)
spec = explicit["gate_kpis"]["cpcv"]["risk_kpis"]["cvar"]
spec["enabled"] = True
spec["threshold"] = 0.70
spec["allow_positive_tail_floor"] = True
cvar = ensure_gate_kpi_profiles(explicit)["cpcv"]["risk_kpis"]["cvar"]
req(abs(float(cvar["threshold"]) - 0.70) < 1e-12, "explicit positive CVaR floor was rewritten")
req("migrated_legacy_positive_tail_floor_from" not in cvar, "explicit positive CVaR floor incorrectly marked as legacy migration")
ensure_risk_kpi_config(risk_cfg_for_gate(explicit, "cpcv"))

# The canonical low-level sign guard remains fail-closed when bypassing gate migration.
direct = deepcopy(CFG)
direct["acceptance"]["risk_kpis"]["cvar"]["enabled"] = True
direct["acceptance"]["risk_kpis"]["cvar"]["threshold"] = 0.80
direct["acceptance"]["risk_kpis"]["cvar"]["allow_positive_tail_floor"] = False
try:
    ensure_risk_kpi_config(direct)
except ValueError as exc:
    req("CVAR_SIGN_SEMANTICS" in str(exc), "wrong direct CVaR guard failure")
else:
    raise AssertionError("direct invalid positive CVaR floor did not fail closed")

print("V1.3.4 CVAR LEGACY MIGRATION SELFTEST PASS")

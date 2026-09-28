from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
sys.path.insert(0, str(ROOT))

from acceptance.runners.owner_mtf4_strategy_acceptance import _build_backtest_ini, _append_acceptance_inputs


def req(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


request = {
    "symbol": "XAUUSD",
    "period": "M15",
    "from_date": "2024.01.01",
    "to_date": "2024.06.30",
    "deposit": 10000.0,
    "leverage": 100,
    "model": 0,
}
control = _build_backtest_ini(
    expert="MAX\\Max_MTF",
    set_name="CONTROL.set",
    request=request,
    report_name="CONTROL.xml",
)
challenger = _build_backtest_ini(
    expert="MAX\\Max_MTF",
    set_name="CHALLENGER.set",
    request=request,
    report_name="CHALLENGER.xml",
)


def parse_ini(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("[") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k] = v
    return out


a = parse_ini(control)
b = parse_ini(challenger)
for key in {
    "Expert", "Symbol", "Period", "Deposit", "Leverage", "Model",
    "ExecutionMode", "Optimization", "FromDate", "ToDate", "ForwardMode",
    "ReplaceReport", "ShutdownTerminal", "UseCloud", "Visual",
}:
    req(a[key] == b[key], f"control/challenger tester invariant mismatch: {key}")

req(a["ExpertParameters"] != b["ExpertParameters"], "control/challenger fixed presets must differ")
req(a["Report"] != b["Report"], "control/challenger reports must remain separate")
req(a["Period"] == "M15", "final acceptance primary timeframe is M15")
req(a["Optimization"] == "0", "final acceptance uses fixed-point backtests")

control_inputs = _append_acceptance_inputs(
    "InpUseMtfStrategy=false\n", metrics_file="control.csv", audit_file=""
)
challenger_inputs = _append_acceptance_inputs(
    "InpUseMtfStrategy=true\n", metrics_file="challenger.csv", audit_file="audit.csv"
)
req("InpAcceptanceMetricsFile=control.csv" in control_inputs, "control metrics evidence enabled")
req("InpMtf4AuditFile=\n" in control_inputs, "control MTF role audit disabled")
req("InpAcceptanceMetricsFile=challenger.csv" in challenger_inputs, "challenger metrics evidence enabled")
req("InpMtf4AuditFile=audit.csv" in challenger_inputs, "challenger MTF role audit enabled")

runner_path = ROOT / "acceptance" / "runners" / "owner_mtf4_strategy_acceptance.py"
runner = runner_path.read_text(encoding="utf-8")
for token in (
    "source_binding(require_main=True)",
    "control_params={k:params[k] for k in ABSOLUTE_BOUNDS}",
    "challenger_hard_gates(mtf,hard)",
    "replay_mtf4_audit(audit_archive)",
    "before_registry=_registry_snapshot()",
    "after_registry=_registry_snapshot()",
    "OWNER_ACCEPTANCE_MUTATED_STRATEGY_CHAMPION",
    "OWNER_ACCEPTANCE_MUTATED_STRATEGY_REGISTRY",
    '"automatic_promotion":False',
    '"authority":"IDENTICAL_SYMBOL_WINDOW_COST_MODEL_AND_LEGACY_PARAMETER_VECTOR"',
):
    req(token in runner, "Owner acceptance invariant missing: " + token)

for forbidden in (
    "promote_strategy_challenger(",
    "persist_optimizer_champion_authority(",
    "register_optimizer_challenger(",
):
    req(forbidden not in runner, "Owner acceptance must not mutate lifecycle: " + forbidden)

gitignore = (PKG / ".gitignore").read_text(encoding="utf-8")
req("owner_acceptance/" in gitignore, "Owner acceptance evidence remains outside public Git")

print("V206_MTF4_OWNER_ACCEPTANCE_HARNESS PASS")

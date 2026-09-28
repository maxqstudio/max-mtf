from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')
WORKER=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
JOBS=(ROOT/'strategy/strategy_optimizer_jobs.py').read_text(encoding='utf-8')
STRATEGY=(ROOT/'strategy/strategy_optimizer.py').read_text(encoding='utf-8')

def req(cond,msg):
    if not cond: raise AssertionError(msg)

# v0.8.3 has one contextual START/RESUME/STOP authority. No separate Recovery or manual Continue.
req('RECOVER LATEST MT5 RESULT' not in APP and 'RESUME FROM MT5 REPORT' not in APP,'legacy recovery buttons must be removed')
req('RESUME AUTO OPTIMIZER' in APP and 'CONTINUE NEXT ROUND' not in APP,'Resume must exist and manual Continue must not')
req('continue_strategy_optimizer_next_round' not in APP and 'continue_next_round_job' not in JOBS,'manual next-round authority must not exist')

# Scientist report and route use the frozen request, not mutable live state.
req('frozen_request=(current or {}).get("request")' in APP,'Scientist Optimizer Report must use frozen request')
req('frozen_request.get("scientist_assist"' in APP,'Scientist assistance provenance must come from frozen request')
req('No narrative reason recorded' not in APP and 'No narrative reason recorded' not in WORKER,'Scientist evidence must never emit ambiguous no-reason fallback')
req('sanitize_scientist_llm_config' in STRATEGY and '"scientist_llm"' in STRATEGY,'non-secret Scientist route config must be frozen')

# Worker distinguishes all three Scientist paths and persists explicit provenance.
for mode in ('DETERMINISTIC_ONLY','SCIENTIST_PROPOSAL','DETERMINISTIC_FALLBACK'):
    req(mode in WORKER,f'{mode} Scientist path missing')
req('actual_llm_call' in WORKER and 'validation' in WORKER and 'scientist_error' in WORKER,'Scientist call/validation/fallback evidence incomplete')
req('Scientist route is not configured' in STRATEGY,'unavailable route must be explicit')

# No-winner automatically continues while round budget remains; winner is a hard stop.
req('ROUND_COMPLETE_NO_CHAMPION' in WORKER and 'NO_CHAMPION_MAX_ROUNDS' in WORKER,'automatic no-winner lifecycle states missing')
req('while True:' in WORKER and 'Automatically refining and continuing' in WORKER,'no-winner must auto-refine/continue within frozen max_rounds')
req('Hard stop contract: once an eligible winner exists' in WORKER,'eligible winner must hard-stop before Scientist/later rounds')
req('if ch is not None:' in WORKER and 'return _apply_winner' in WORKER,'winner short-circuit missing')

# Frozen Owner KPI remains the eligibility/no-winner authority, including negative custom threshold when Owner chooses it.
req('exp_min=float(kpi.get("min_expectancy_r"' in WORKER,'frozen Expectancy R threshold missing')
req('near=best_near_miss(rows)' in WORKER,'Near miss must use per-row frozen KPI requirements')
req('optimizer_kpi_policy({' in APP and 'strategy_opt_kpi_exp' in APP,'live Optimizer KPI must be frozen into the request at START')

print('V082_OPTIMIZER_UI_SCIENTIST_RECOVERY_PASS')

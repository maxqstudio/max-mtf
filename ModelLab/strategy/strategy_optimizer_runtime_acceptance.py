from __future__ import annotations
import json,math,re,sys,hashlib
from datetime import datetime, timezone
from pathlib import Path
from core.project_paths import MODELLAB_ROOT
from strategy.strategy_optimizer import EA_SOURCE, RUNS_ROOT, EVIDENCE_ROOT, OPTIMIZER_PF_MIN, OPTIMIZER_RF_MIN, OPTIMIZER_EXPECTANCY_R_MIN, OPTIMIZER_WEIGHTED_R_MIN, parse_optimizer_metrics_csv
from strategy.strategy_optimizer_jobs import latest_job

OUT=MODELLAB_ROOT/'evidence/current/STRATEGY_OPTIMIZER_V2_OWNER_RUNTIME_ACCEPTANCE.json'

def fail(gate:str,detail:str)->int:
    payload={'schema':'MAX_STRATEGY_OPTIMIZER_V2_OWNER_RUNTIME_ACCEPTANCE','status':'FAIL','first_failed_gate':gate,'detail':detail,'generated_utc':datetime.now(timezone.utc).isoformat()}
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8'); print(json.dumps(payload,indent=2)); return 1

def main()->int:
    job=latest_job()
    if not job: return fail('NO_OPTIMIZER_RUN','Run Strategy Optimizer from UI first.')
    jid=str(job.get('job_id') or ''); d=RUNS_ROOT/jid
    status=str(job.get('status') or '')
    if status not in {'STRATEGY_CHALLENGER_FOUND','CHAMPION_FOUND','NO_CHAMPION_MAX_ROUNDS'}: return fail('NON_TERMINAL_OR_FAILED_STATUS',f'Latest status={status}')
    evidence=EVIDENCE_ROOT/jid
    log=evidence/'metaeditor_compile.log'
    if not log.exists(): return fail('METAEDITOR_LOG_MISSING',str(log))
    txt=log.read_text(encoding='utf-8',errors='ignore')
    matches=list(re.finditer(r'Result:\s*(\d+)\s+errors?\s*,\s*(\d+)\s+warnings?',txt,re.I))
    if not matches: return fail('METAEDITOR_COMPILE_SUMMARY_MISSING','Explicit MetaEditor Result summary is required')
    m=matches[-1]
    if int(m.group(1))>0: return fail('METAEDITOR_COMPILE_ERRORS',m.group(0))
    compile_ctx=evidence/'compile_context.json'
    if not compile_ctx.exists(): return fail('METAEDITOR_COMPILE_CONTEXT_MISSING',str(compile_ctx))
    try: cc=json.loads(compile_ctx.read_text(encoding='utf-8'))
    except Exception as exc: return fail('METAEDITOR_COMPILE_CONTEXT_INVALID',str(exc))
    ex5=Path(str(cc.get('expected_ex5') or ''))
    if not ex5.exists(): return fail('METAEDITOR_EX5_MISSING',str(ex5))
    rounds=job.get('rounds') if isinstance(job.get('rounds'),list) else []
    if not rounds: return fail('NO_COMPLETED_MT5_ROUND','No round evidence in status.json')
    for r in rounds:
        report=Path(str(r.get('report') or ''))
        if not report.exists() or report.suffix.lower()!='.xml' or report.stat().st_size<50:
            return fail('MT5_XML_REPORT_MISSING',str(report))
        audit=r.get('eligibility_audit') if isinstance(r.get('eligibility_audit'),dict) else {}
        thresholds=audit.get('thresholds') if isinstance(audit.get('thresholds'),dict) else {}
        if 'min_weighted_r' not in thresholds:
            return fail('WEIGHTED_R_GATE_EVIDENCE_MISSING',f'round={r.get("round")}')
        metrics=Path(str(r.get('optimizer_metrics_path') or ''))
        if not metrics.is_file() or metrics.stat().st_size<20:
            return fail('WEIGHTED_R_SIDECAR_MISSING',f'round={r.get("round")} path={metrics}')
        expected_sha=str(r.get('optimizer_metrics_sha256') or '')
        actual_sha=hashlib.sha256(metrics.read_bytes()).hexdigest()
        if not expected_sha or actual_sha!=expected_sha:
            return fail('WEIGHTED_R_SIDECAR_HASH_MISMATCH',f'round={r.get("round")} expected={expected_sha} actual={actual_sha}')
        nonce=int(r.get('optimizer_run_nonce') or 0)
        if nonce<=0:
            return fail('WEIGHTED_R_RUN_NONCE_MISSING',f'round={r.get("round")}')
        try:
            metric_rows=parse_optimizer_metrics_csv(metrics,expected_nonce=nonce)
        except Exception as exc:
            return fail('WEIGHTED_R_SIDECAR_INVALID',f'round={r.get("round")} {exc}')
        parsed_passes=int(audit.get('parsed_passes') or r.get('passes') or 0)
        if parsed_passes<=0 or len(metric_rows)!=parsed_passes:
            return fail('WEIGHTED_R_PASS_PARITY_MISMATCH',f'round={r.get("round")} xml_passes={parsed_passes} metric_passes={len(metric_rows)}')
    req=job.get('request') or {}
    frozen=req.get('ea_source') if isinstance(req.get('ea_source'),dict) else {}
    source_sha=str(frozen.get('sha256') or '')
    if not source_sha: return fail('CANONICAL_EA_IDENTITY_MISSING','request.ea_source.sha256 missing')
    if not EA_SOURCE.exists(): return fail('CANONICAL_EA_SOURCE_MISSING',str(EA_SOURCE))
    current_source_sha=hashlib.sha256(EA_SOURCE.read_bytes()).hexdigest()
    if status!='CHAMPION_FOUND':
        if str(cc.get('canonical_source_sha256') or '')!=source_sha or str(cc.get('deployed_source_sha256') or '')!=source_sha or current_source_sha!=source_sha:
            return fail('CANONICAL_EA_DEPLOYMENT_HASH_MISMATCH','Optimizer must not mutate current Strategy Champion; frozen source, package EA and MT5 deployment must remain byte-identical')
    if str(req.get('symbol') or '').lower()==str(req.get('confirm_symbol') or '').lower() or not str(req.get('confirm_symbol') or '').strip():
        return fail('SEVEN_FAMILY_CONFIRM_SYMBOL_INVALID','Confirm Symbol blank/equal to Main Symbol')
    if status=='STRATEGY_CHALLENGER_FOUND':
        ch=job.get('strategy_challenger') or {}; entry=job.get('strategy_challenger_entry') or {}
        try:
            pf=float(ch.get('profit_factor')); rf=float(ch.get('recovery_factor')); er=float(ch.get('expectancy_r')); wr=float(ch.get('weighted_r')); trades=int(ch.get('trades') or 0)
        except Exception:
            return fail('STRATEGY_CHALLENGER_METRIC_MISSING','Strategy Challenger metrics are missing or malformed')
        sample=req.get('optimizer_trade_sample') or {}; kpi=sample.get('kpi_profile') or {}
        min_trades=int(sample.get('minimum_trades') or 1)
        min_pf=float(kpi.get('min_profit_factor',OPTIMIZER_PF_MIN)); min_rf=float(kpi.get('min_recovery_factor',OPTIMIZER_RF_MIN)); min_er=float(kpi.get('min_expectancy_r',OPTIMIZER_EXPECTANCY_R_MIN)); min_wr=float(kpi.get('min_weighted_r',OPTIMIZER_WEIGHTED_R_MIN))
        if not (trades>=min_trades and all(math.isfinite(x) for x in (pf,rf,er,wr)) and pf>=min_pf and rf>=min_rf and er>=min_er and wr>=min_wr):
            return fail('STRATEGY_CHALLENGER_HARD_GATE_FAIL','Registered Strategy Challenger does not satisfy frozen Optimizer gates')
        if not str(entry.get('challenger_id') or '').startswith('STRAT-'):
            return fail('STRATEGY_CHALLENGER_ID_INVALID',str(entry.get('challenger_id')))
        for key in ('ea_file','set_file','metadata_file'):
            q=Path(str(entry.get(key) or ''))
            if not q.is_file(): return fail('STRATEGY_CHALLENGER_ARTIFACT_MISSING',f'{key}={q}')
        if hashlib.sha256(Path(entry['ea_file']).read_bytes()).hexdigest()!=str(entry.get('ea_sha256') or ''):
            return fail('STRATEGY_CHALLENGER_EA_HASH_MISMATCH',str(entry.get('ea_file')))
        if hashlib.sha256(Path(entry['set_file']).read_bytes()).hexdigest()!=str(entry.get('set_sha256') or ''):
            return fail('STRATEGY_CHALLENGER_SET_HASH_MISMATCH',str(entry.get('set_file')))
    if status=='CHAMPION_FOUND':
        ch=job.get('champion') or {}
        try:
            pf=float(ch.get('profit_factor')); rf=float(ch.get('recovery_factor')); er=float(ch.get('expectancy_r')); wr=float(ch.get('weighted_r')); trades=int(ch.get('trades') or 0)
        except Exception:
            return fail('CHAMPION_METRIC_MISSING','Champion metrics are missing or malformed')
        sample=req.get('optimizer_trade_sample') or {}; kpi=sample.get('kpi_profile') or {}
        min_trades=int(sample.get('minimum_trades') or 1)
        min_pf=float(kpi.get('min_profit_factor',OPTIMIZER_PF_MIN)); min_rf=float(kpi.get('min_recovery_factor',OPTIMIZER_RF_MIN)); min_er=float(kpi.get('min_expectancy_r',OPTIMIZER_EXPECTANCY_R_MIN)); min_wr=float(kpi.get('min_weighted_r',OPTIMIZER_WEIGHTED_R_MIN))
        if not (
            trades >= min_trades and all(math.isfinite(x) for x in (pf,rf,er,wr))
            and pf >= min_pf
            and rf >= min_rf
            and er >= min_er
            and wr >= min_wr
        ):
            return fail('CHAMPION_HARD_GATE_FAIL',f'Champion does not satisfy trades>={min_trades}, PF>={min_pf}, RF>={min_rf}, MeanR>={min_er}, WeightedR>={min_wr} with finite metrics')
        for name in ('champion.json','ea_champion_apply.json'):
            if not (d/name).exists(): return fail('CHAMPION_ARTIFACT_MISSING',name)
        try: apply=json.loads((d/'ea_champion_apply.json').read_text(encoding='utf-8'))
        except Exception as exc: return fail('EA_CHAMPION_APPLY_INVALID',str(exc))
        if str(apply.get('before_sha256') or '')!=source_sha:
            return fail('EA_CHAMPION_APPLY_BASE_MISMATCH','Champion apply must start from frozen request EA')
        after_sha=str(apply.get('after_sha256') or '')
        if not after_sha or current_source_sha!=after_sha:
            return fail('EA_CHAMPION_APPLY_SOURCE_MISMATCH','Current EA_v2_00/baseline must equal champion-applied source')
        if str(apply.get('mutation_scope') or '')!='WHITELISTED_OPTIMIZER_INPUT_DEFAULTS_ONLY':
            return fail('EA_CHAMPION_APPLY_SCOPE_INVALID','Only optimizer-owned input defaults may change')
        if str(cc.get('canonical_source_sha256') or '')!=after_sha or str(cc.get('deployed_source_sha256') or '')!=after_sha:
            return fail('EA_CHAMPION_DEPLOYMENT_HASH_MISMATCH','Champion-updated EA source and MT5 deployment must be byte-identical')
        ev_ch=evidence/'champion'
        for name in ('ea_before_champion.mq5','ea_after_champion.mq5','ea_champion_apply.json','champion.json'):
            if not (ev_ch/name).exists(): return fail('CHAMPION_EVIDENCE_MISSING',name)
    payload={'schema':'MAX_STRATEGY_OPTIMIZER_V2_OWNER_RUNTIME_ACCEPTANCE','status':'PASS','first_failed_gate':None,'job_id':jid,'optimizer_status':status,'rounds':len(rounds),'strategy_challenger_found':status=='STRATEGY_CHALLENGER_FOUND','legacy_champion_found':status=='CHAMPION_FOUND','generated_utc':datetime.now(timezone.utc).isoformat(),'run_dir':str(d),'evidence_dir':str(evidence)}
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8'); print(json.dumps(payload,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())

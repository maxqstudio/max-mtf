from __future__ import annotations
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data.labels import build_labels
from models.model_lab import load_cfg, load_training_csv, research_region, candidate_cv, sha256_file
from models.models import CandidateSpec
from research.kpi import walk_forward_acceptance
from host.preflight import period_label


def _load(path: Path): return json.loads(path.read_text(encoding='utf-8'))
def _write(path: Path, obj): path.write_text(json.dumps(obj,indent=2,default=str),encoding='utf-8')


def run_guided_research(audit_run_dir, csv_path, config_path='config.json', out_dir='runs', progress=None):
    audit_run=Path(audit_run_dir); mp=audit_run/'model_manifest.json'
    if not mp.exists(): raise ValueError('Audit run tidak memiliki model_manifest.json')
    am=_load(mp)
    if str(am.get('status'))!='FEATURE_LABEL_AUDIT_READY': raise ValueError('Guided Research hanya menerima FEATURE_LABEL_AUDIT_READY')
    report=_load(audit_run/'feature_label_audit.json')
    csv_path=str(csv_path); actual=sha256_file(csv_path); expected=str(am.get('source_csv_sha256') or '')
    if expected and actual!=expected: raise ValueError('CSV berbeda dari lineage audit. Hash mismatch.')
    cfg=load_cfg(audit_run/'run_config.json' if (audit_run/'run_config.json').exists() else config_path)
    current=load_cfg(config_path); cfg['acceptance']=deepcopy(current.get('acceptance',cfg.get('acceptance',{})))
    raw=load_training_csv(csv_path)
    source_model_id=str(am.get('model_source_run_id') or '')
    model_run=Path(out_dir)/source_model_id
    mm=_load(model_run/'model_manifest.json') if (model_run/'model_manifest.json').exists() else am
    spec=CandidateSpec(str(mm.get('model_family')),str(mm.get('model_name')),dict(mm.get('hyperparameters') or {}))
    hypotheses=list(report.get('guided_hypotheses') or [])
    if not hypotheses: raise ValueError('Audit tidak menghasilkan bounded hypotheses')
    run_id=datetime.now(timezone.utc).strftime('GUIDED_%Y%m%d_%H%M%S_UTC'); out=Path(out_dir)/run_id; out.mkdir(parents=True,exist_ok=True)
    rows=[]
    total=len(hypotheses)
    for i,h in enumerate(hypotheses,1):
        hc=deepcopy(cfg); hc['label']=deepcopy(h.get('label') or cfg['label']); hc['feature_research']={'zero_features':list(h.get('zero_features') or []),'schema':'CP32_ZERO_MASK_V1'}
        # No downstream/locked metric is calculated. The exact same upstream research-region contract used by Discovery is reused here.
        labeled=build_labels(raw,hc); pre,_retired,region_meta=research_region(labeled,hc)
        if progress: progress({'stage':'guided','current':i-1,'total':total,'message':f"Guided OOF {i}/{total} · {h.get('name')}"})
        try:
            cv=candidate_cv(spec,pre,hc)
            acc=walk_forward_acceptance(cv,hc)
            row={
                'index':i,'name':str(h.get('name')),'reason':str(h.get('reason','')),'label':hc['label'],'zero_features':hc['feature_research']['zero_features'],'research_region':region_meta,
                **cv,'cv_gate_pass':bool(acc.get('passed')),'cv_gate_reasons':list(acc.get('reasons') or []),'cv_first_failed_gate':acc.get('first_failed_gate'),
            }
        except Exception as e:
            row={'index':i,'name':str(h.get('name')),'reason':str(h.get('reason','')),'label':hc['label'],'zero_features':hc['feature_research']['zero_features'],'research_region':region_meta,'cv_gate_pass':False,'cv_gate_reasons':['EVALUATION_ERROR'],'error':str(e),'selection_score':-1e99}
        rows.append(row)
        if progress: progress({'stage':'guided','current':i,'total':total,'message':f"{h.get('name')} · {'PASS' if row.get('cv_gate_pass') else 'FAIL'}",'guided_row':{k:row.get(k) for k in ('name','cv_gate_pass','median_max_drawdown_r','median_recovery_factor','median_profit_factor','median_expectancy_r','worst_expectancy_r','total_validation_trades','cv_first_failed_gate')}})
    rows.sort(key=lambda r:(bool(r.get('cv_gate_pass')),float(r.get('selection_score',-1e99))),reverse=True)
    winner=rows[0]; passed=bool(winner.get('cv_gate_pass'))
    status='GUIDED_RESEARCH_READY' if passed else 'GUIDED_RESEARCH_REJECTED'
    recommended=deepcopy(cfg); recommended['label']=deepcopy(winner.get('label') or cfg['label']); recommended['feature_research']={'zero_features':list(winner.get('zero_features') or []),'schema':'CP32_ZERO_MASK_V1'}
    recommended.setdefault('agent',{})['skip_locked_test']=True
    # Guided Research is hypothesis selection only. Full model search is a separate button, but remains one legal route.
    _write(out/'guided_leaderboard.json',rows); _write(out/'recommended_config.json',recommended)
    manifest={
        'run_id':run_id,'run_type':'GUIDED_FEATURE_LABEL_RESEARCH','status':status,'supervisor_stage':'WAITING_NEW_GENERATION_RESEARCH' if passed else 'GUIDED_RESEARCH_REJECTED',
        'reject_reasons':[] if passed else list(winner.get('cv_gate_reasons') or ['NO_GUIDED_HYPOTHESIS_PASSED']),
        'source_run_id':am.get('source_run_id'),'audit_run_id':am.get('run_id'),'model_source_run_id':source_model_id,
        'source_csv_sha256':actual,'dataset_provenance':{'symbol':str(raw['symbol'].iloc[0]),'period':int(raw['period'].iloc[0]),'timeframe':period_label(raw['period'].iloc[0]),'source_start':str(raw['signal_time'].min()),'source_end':str(raw['signal_time'].max())},
        'symbol':str(raw['symbol'].iloc[0]),'period':int(raw['period'].iloc[0]),'timeframe':period_label(raw['period'].iloc[0]),
        'model_family':spec.family,'model_name':spec.name,'hyperparameters':spec.params,'label_policy':recommended['label'],'feature_research':recommended['feature_research'],
        'cv_selection':winner,'cv_acceptance':{'passed':passed,'reasons':list(winner.get('cv_gate_reasons') or []),'first_failed_gate':winner.get('cv_first_failed_gate')},
        'guided_hypotheses_evaluated':len(rows),'retired_locked_test_accessed':False,'generated_utc':datetime.now(timezone.utc).isoformat(),
        'agent':{'locked_test_opened_once':False,'retired_locked_test_accessed':False,'planner':'guided_feature_label_v1'},
    }
    _write(out/'model_manifest.json',manifest); _write(out/'supervisor_state.json',{'stage':manifest['supervisor_stage'],'run_id':run_id,'next_required':'START_NEW_GENERATION_RESEARCH' if passed else 'NEW_HYPOTHESIS_REQUIRED','updated_utc':datetime.now(timezone.utc).isoformat()})
    with (out/'REPORT.md').open('w',encoding='utf-8') as f:
        f.write(f"# Guided Feature + Label Research {run_id}\n\n**Status:** {status}\n\n**Audit:** {am.get('run_id')}\n\n")
        f.write('Retired locked test accessed: **FALSE**. All hypotheses were evaluated on upstream OOF only.\n\n')
        f.write(f"Best hypothesis: **{winner.get('name')}** · PASS={passed} · first failed gate `{winner.get('cv_first_failed_gate')}`.\n\n")
        f.write('**Next required:** '+('START_NEW_GENERATION_RESEARCH' if passed else 'NEW_HYPOTHESIS_REQUIRED')+'\n')
    if progress: progress({'stage':'done','current':total,'total':total,'message':status})
    return {'run':str(out),'status':status,'manifest':manifest,'winner':winner,'recommended_config':recommended}

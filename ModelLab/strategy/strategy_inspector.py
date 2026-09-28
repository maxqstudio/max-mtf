from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pandas as pd
from data.dataset_integrity import read_csv_auto


def _read(path: Path, default=None):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return {} if default is None else default


def _dataset_summary(path: Path|None) -> dict:
    if not path or not Path(path).exists(): return {'available':False}
    p=Path(path)
    try:
        df=read_csv_auto(p,usecols=['symbol','period','signal_time'])
        ts=pd.to_datetime(df['signal_time'],errors='coerce')
        years=ts.dt.year.value_counts().sort_index()
        return {
            'available':True,'path':str(p),'symbol':str(df['symbol'].iloc[0]) if len(df) else None,
            'period':int(df['period'].iloc[0]) if len(df) else None,'rows':int(len(df)),
            'start':str(ts.min()),'end':str(ts.max()),'rows_by_year':{str(int(k)):int(v) for k,v in years.items() if not pd.isna(k)}
        }
    except Exception as e:
        return {'available':False,'path':str(p),'error':str(e)}


def _factory_summary(factory_dir: Path|None) -> dict:
    if not factory_dir or not Path(factory_dir).exists(): return {'available':False}
    fd=Path(factory_dir); fm=_read(fd/'factory_manifest.json',{})
    pool=_read(fd/'candidate_pool.json',[]); tl=_read(fd/'tournament_leaderboard.json',[])
    ts=_read(fd/'tournament_survivors.json',[]); mc=_read(fd/'monte_carlo_evidence.json',{}); fw=_read(fd/'forward_leaderboard.json',[]); champion=_read(fd/'champion.json',{})
    latest={}
    ev=fm.get('forward_evidence_file')
    if ev: latest=_read(fd/ev,{})
    return {
        'available':True,'factory_id':fd.name,'status':fm.get('status'),'stage':fm.get('stage'),
        'qualified_candidates':fm.get('qualified_candidates',len(pool)),'target_candidates':fm.get('target_candidates'),
        'total_experiments':fm.get('total_experiments'),'max_total_experiments':fm.get('max_total_experiments'),
        'discovery':fm.get('discovery'),'tournament_contract':fm.get('tournament_contract'),'forward_contract':fm.get('forward_contract'),
        'research_contract_hash':fm.get('research_contract_hash'),'global_memory':fm.get('global_memory'),'compute_plan_file':fm.get('compute_plan_file'),
        'pool':[{'pool_id':c.get('pool_id'),'family':c.get('family'),'name':c.get('name'),'params':c.get('params'),'take_threshold':c.get('take_threshold'),'metrics':c.get('discovery_metrics')} for c in pool[:12]],
        'tournament':[{'pool_id':r.get('pool_id'),'family':r.get('family'),'name':r.get('name'),'metrics':r.get('metrics'),'yearly':r.get('yearly'),'acceptance':r.get('acceptance')} for r in tl[:12]],
        'tournament_survivors':[{'pool_id':r.get('pool_id'),'family':r.get('family'),'name':r.get('name')} for r in ts],
        'monte_carlo':mc or None,
        'forward':[{'pool_id':r.get('pool_id'),'family':r.get('family'),'name':r.get('name'),'metrics':r.get('metrics'),'acceptance':r.get('acceptance')} for r in fw],
        'champion':champion or None,'latest_forward_evidence':latest or None,
    }


def build_readonly_strategy_context(cfg: dict, dataset: str|Path|None=None, factory_dir: str|Path|None=None, app_dir: str|Path|None=None) -> dict:
    """Read-only evidence view for the Scientist. Never mutates config/data/lineage."""
    strategy={
        'label':cfg.get('label',{}),'deployment':cfg.get('deployment',{}),'acceptance':cfg.get('acceptance',{}),
        'trade_sample_policy':cfg.get('trade_sample_policy',{}),'champion_factory':cfg.get('champion_factory',{}),
        'enabled_models':{k:v for k,v in (cfg.get('models') or {}).items() if isinstance(v,bool)},
        'split':cfg.get('split',{}),'score_policy':cfg.get('score_policy',{}),
    }
    raw=json.dumps(strategy,sort_keys=True,separators=(',',':'),default=str).encode('utf-8')
    features=[]
    if app_dir:
        fp=Path(app_dir).parent/'EA_v2_00'/'baseline'/'feature_contract.csv'
        if fp.exists():
            try: features=pd.read_csv(fp).head(100).to_dict(orient='records')
            except Exception: features=[]
    return {
        'authority':'READ_ONLY_DETERMINISTIC_STRATEGY','mutation_allowed':False,
        'strategy_contract_sha256':hashlib.sha256(raw).hexdigest(),
        'strategy_contract':strategy,'feature_contract':features,
        'dataset':_dataset_summary(Path(dataset) if dataset else None),
        'factory':_factory_summary(Path(factory_dir) if factory_dir else None),
        'scientist_instruction':'Assess whether strategy changes are supported by evidence. Recommend hypotheses/ablations; never modify deterministic strategy directly.',
    }

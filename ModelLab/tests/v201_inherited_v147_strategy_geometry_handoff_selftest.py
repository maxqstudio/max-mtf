from __future__ import annotations
import json, tempfile, sys
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from core.inherited_v147 import (
    canonical_candidate_cfg, prove_pool_full_wfa_geometry, contracts_equal_except_strategy_geometry,
    archive_uncommitted_cpcv_surfaces, sha256_file,
)
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry



def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def candidate(i:int):
    return {
        'pool_id':f'CAND_{i:02d}','source_run':f'RUN_{i:02d}','family':'xgboost','name':f'm{i}','params':{'max_depth':4+i%3},
        'training_seed':42,'take_threshold':0.65,
        'research_overrides':{'label':{'sl_atr':1.8,'tp_atr':2.7,'horizon_bars':24,'tie_policy':'sl_first'},'feature_research':{'enabled':True}},
        'wfa_evidence':{'cv_gate_pass':True,'fidelity_stage':'FULL_WFA','selection_score':100-i},
        'discovery_acceptance':{'passed':True,'authority':'FULL_WFA_ONLY'},
    }


# Temporal guards use MaxHold as a minimum, never as forced equality.
class _Series(list):
    def astype(self, _): return _Series(float(x) for x in self)
    def isna(self): return _BoolSeries(False for _ in self)
    def map(self, fn): return _Series(fn(x) for x in self)
    def any(self): return any(self)
    def __invert__(self): return _BoolSeries(not bool(x) for x in self)
class _BoolSeries(list):
    def any(self): return any(self)
    def __invert__(self): return _BoolSeries(not bool(x) for x in self)
class _Frame:
    def __init__(self, **cols): self._cols=cols; self.columns=set(cols)
    def __getitem__(self, k): return _Series(self._cols[k])

df=_Frame(sl_atr=[3.2,3.2],tp_atr=[4.8,4.8],max_hold_bars=[54,54])
weak_cfg={'split':{'purge_bars':24,'embargo_bars':24}}
weak_out,_=synchronize_cfg_with_dataset_geometry(weak_cfg,df,require_runtime_authority_match=False)
req(weak_out['split']=={'purge_bars':54,'embargo_bars':54},'Case A: stale 24/24 temporal guards are lifted to max_hold=54')
strict_cfg={'split':{'purge_bars':72,'embargo_bars':96}}
strict_out,_=synchronize_cfg_with_dataset_geometry(strict_cfg,df,require_runtime_authority_match=False)
req(strict_out['split']=={'purge_bars':72,'embargo_bars':96},'Case B: intentional stricter 72/96 temporal guards are preserved above max_hold=54')
req(strict_out['strategy_geometry']['temporal_guard']['minimum_from_max_hold_bars']==54,'temporal guard records max_hold as minimum authority')

base={'label':{'sl_atr':1.8,'tp_atr':2.7,'horizon_bars':24,'base_knob':'keep'},'split':{'purge_bars':54,'embargo_bars':54},'strategy_geometry':{'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':54},'seed':11}
c= candidate(1)
out=canonical_candidate_cfg(base,c)
req(out['strategy_geometry']['sl_atr']==3.2 and out['strategy_geometry']['tp_atr']==4.8 and out['strategy_geometry']['max_hold_bars']==54,'candidate replay keeps canonical 3.2/4.8/54 Strategy geometry')
req(out['split']['purge_bars']==54 and out['split']['embargo_bars']==54,'candidate replay keeps purge/embargo=54')
req(all(k not in out['label'] for k in ('sl_atr','tp_atr','horizon_bars','max_hold_bars')),'stale candidate label geometry cannot regain authority')
req(out['label']['tie_policy']=='sl_first' and out['feature_research']['enabled'] is True,'non-geometry candidate research overrides are preserved')

old={'label':{'sl_atr':1.8,'tp_atr':2.7,'horizon_bars':24,'x':1},'split':{'purge_bars':24,'embargo_bars':24,'groups':6},'deployment':{'a':1}}
new={'label':{'x':1},'split':{'purge_bars':54,'embargo_bars':54,'groups':6},'deployment':{'a':1}}
req(contracts_equal_except_strategy_geometry(old,new),'geometry-only inherited drift is recognized narrowly')
bad=deepcopy(new); bad['deployment']['a']=2
req(not contracts_equal_except_strategy_geometry(old,bad),'unrelated scientific drift is not disguised as geometry repair')

with tempfile.TemporaryDirectory() as td0:
    fd=Path(td0)/'FACTORY_FIXTURE'; (fd/'research_runs').mkdir(parents=True)
    snapshot=fd/'discovery_immutable.csv'; snapshot.write_text('contract;symbol;sl_atr;tp_atr;max_hold_bars\nCP32;XAUUSD;3.2;4.8;54\n',encoding='utf-8')
    snapsha=sha256_file(snapshot)
    pool=[candidate(i) for i in range(1,13)]
    pool_path=fd/'candidate_pool.json'; pool_path.write_text(json.dumps(pool,sort_keys=True),encoding='utf-8'); before=pool_path.read_bytes()
    source_cfg={'label':{},'split':{'purge_bars':54,'embargo_bars':54},'strategy_geometry':{'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':54},'research_window':{'authority_snapshot_sha256':snapsha}}
    for row in pool:
        d=fd/'research_runs'/row['source_run']; d.mkdir(parents=True); (d/'run_config.json').write_text(json.dumps(source_cfg),encoding='utf-8')
        (d/'cv_leaderboard.json').write_text(json.dumps([{'family':row['family'],'name':row['name'],'params':row['params'],'cv_gate_pass':True,'fidelity_stage':'FULL_WFA'}]),encoding='utf-8')
    proofs=prove_pool_full_wfa_geometry(fd,pool,base)
    req(len(proofs)==12,'12 committed candidates are preserved with source Full-WFA geometry proof')
    req(pool_path.read_bytes()==before,'source proof does not mutate committed candidate Pool')
    req(all(p['geometry']=={'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':54,'purge_bars':54,'embargo_bars':54} for p in proofs),'all source Full-WFA evidence proves canonical geometry')

    # Missing source-run proof must fail closed.
    missing=deepcopy(pool); missing[0]['source_run']='MISSING'
    try: prove_pool_full_wfa_geometry(fd,missing,base); accepted=True
    except RuntimeError: accepted=False
    req(not accepted,'missing Full-WFA source-run proof is rejected')

    # run_config alone is insufficient: source-run must also prove Full-WFA PASS.
    lb=fd/'research_runs'/pool[1]['source_run']/'cv_leaderboard.json'; lb_saved=lb.read_text(); lb.unlink()
    try: prove_pool_full_wfa_geometry(fd,pool,base); accepted=True
    except RuntimeError: accepted=False
    req(not accepted,'missing source Full-WFA PASS artifact is rejected even when run_config exists')
    lb.write_text(lb_saved,encoding='utf-8')

    # Mismatched source-run geometry must fail closed.
    q=fd/'research_runs'/pool[0]['source_run']/'run_config.json'; obj=json.loads(q.read_text()); obj['strategy_geometry']['sl_atr']=3.1; q.write_text(json.dumps(obj),encoding='utf-8')
    try: prove_pool_full_wfa_geometry(fd,pool,base); accepted=True
    except RuntimeError: accepted=False
    req(not accepted,'mismatched Full-WFA source-run geometry is rejected')
    q.write_text(json.dumps(source_cfg),encoding='utf-8')

    # A stale uncommitted CPCV plan may be archived; Pool stays byte-identical.
    (fd/'cpcv_finalist_plan.json').write_text(json.dumps({'stage_contract_hash':'STALE'}),encoding='utf-8')
    (fd/'cpcv_live.json').write_text(json.dumps({'split_completed':0}),encoding='utf-8')
    (fd/'cpcv_live_split_results.json').write_text(json.dumps({'rows':[]}),encoding='utf-8')
    arc=archive_uncommitted_cpcv_surfaces(fd,'fixture')
    req(bool(arc['archived']) and not (fd/'cpcv_finalist_plan.json').exists(),'stale CPCV plan can be archived only at zero committed progress')
    req(pool_path.read_bytes()==before,'CPCV contract rebuild path leaves candidate Pool byte-for-byte unchanged')

    # Any live split row is committed progress and must block silent reset.
    (fd/'cpcv_finalist_plan.json').write_text(json.dumps({'stage_contract_hash':'STALE2'}),encoding='utf-8')
    (fd/'cpcv_live_split_results.json').write_text(json.dumps({'rows':[{'split':1,'expectancy_r':0.1}]}),encoding='utf-8')
    try: archive_uncommitted_cpcv_surfaces(fd,'fixture2'); accepted=True
    except RuntimeError: accepted=False
    req(not accepted,'existing committed CPCV split progress cannot be silently reset')

src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
req(src.index('synchronize_cfg_with_dataset_geometry(cfg,_authority_raw)') < src.index('discovery_stage_contract={'),'canonical Strategy geometry resolves before Discovery contract freeze')
req('strip_strategy_geometry_from_label(gcfg.get("label") or {})' in src,'Discovery Pool freezes candidate label overrides without Strategy geometry authority')
print('V201_INHERITED_V147_STRATEGY_GEOMETRY_HANDOFF PASS')

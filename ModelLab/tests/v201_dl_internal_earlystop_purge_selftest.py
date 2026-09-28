from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from models.models import CandidateSpec, make_model, fit_model_indexed

ROOT=Path(__file__).resolve().parents[1]
EVID=ROOT/'evidence/current/V201_TRAINING_SCIENTIFIC_EVIDENCE.json'

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def cfg(h=6):
    return {'models':{'gru_patience':1,'hybrid_oof_inner_folds':2},'cpu_threads':1,
            'strategy_geometry':{'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':int(h)},
            'split':{'purge_bars':int(h),'embargo_bars':int(h)},'compute':{}}

def params(fam):
    base=dict(sequence_length=8,dropout=0.0,learning_rate=.001,batch_size=64,epochs=1,weight_decay=0.0)
    if fam=='gru': return dict(base,hidden_size=8,num_layers=1)
    if fam=='lstm': return dict(base,hidden_size=8,num_layers=1)
    if fam=='tcn': return dict(base,tcn_channels=8,tcn_blocks=1,kernel_size=3)
    if fam in {'transformer','transformer_moe','patchtst','itransformer','tft'}:
        p=dict(base,d_model=8,num_layers=1,attention_heads=2,ffn_mult=2)
        if fam=='transformer_moe': p.update(expert_ffn=16,num_experts=4,top_k=1,router_temperature=1.0,load_balance_coef=.01)
        if fam=='patchtst': p.update(patch_len=4,patch_stride=2)
        if fam=='tft': p.update(tft_lstm_layers=1)
        return p
    raise KeyError(fam)

def check(ev,h):
    req(ev.get('mode')=='PURGED_EARLYSTOP','production temporal path uses purged early-stop mode')
    req(int(ev['effective_horizon_bars'])==h and int(ev['applied_purge_bars'])>=h,'canonical horizon/purge applied')
    req(int(ev['internal_train_latest_target_end_row']) < int(ev['first_internal_validation_row']),'latest train target ends before early-validation decision boundary')
    req(ev.get('overlap_check')=='PASS' and ev.get('validation_context_preserved') is True,'overlap fails closed while causal feature context is preserved')

rng=np.random.default_rng(201); n=210; X=rng.normal(size=(n,8)).astype(np.float32); y=(np.arange(n)%3).astype(np.int64)
family_evidence={}
for fam in ['gru','lstm','tcn','transformer','patchtst','itransformer','tft','transformer_moe']:
    m=make_model(CandidateSpec(fam,f'purge_{fam}',params(fam)),cfg(6))
    fit_model_indexed(m,fam,X,y,np.arange(n),cfg(6))
    ev=dict(m.internal_validation_); check(ev,6); family_evidence[fam]=ev
req(len(family_evidence)==8,'shared production authority exercised across all temporal families')

# Explicit production-path horizon-54 proof matching the canonical MaxHold example.
n54=440; X54=rng.normal(size=(n54,8)).astype(np.float32); y54=(np.arange(n54)%3).astype(np.int64)
m54=make_model(CandidateSpec('gru','horizon54',params('gru')),cfg(54)); fit_model_indexed(m54,'gru',X54,y54,np.arange(n54),cfg(54))
h54_ev=dict(m54.internal_validation_); check(h54_ev,54)
req(int(h54_ev['internal_train_latest_target_end_row']) < int(h54_ev['first_internal_validation_row']),'horizon-54 production fixture proves target outcome cannot overlap early validation')

# Discontinuous CPCV-like authorized complement: original row ids must remain authoritative.
idx=np.r_[np.arange(0,90),np.arange(120,210)]
m=make_model(CandidateSpec('gru','gapped',params('gru')),cfg(6)); fit_model_indexed(m,'gru',X,y,idx,cfg(6))
gap_ev=dict(m.internal_validation_); check(gap_ev,6); req(int(gap_ev['authorized_row_gaps'])>=1,'gapped authorized chronology is not compressed')

# Hybrid temporal encoder inherits the same contract while preserving OOF stacking.
nh=560; Xh=rng.normal(size=(nh,8)).astype(np.float32); yh=(np.arange(nh)%3).astype(np.int64)
hp={'temporal_sequence_length':8,'temporal_hidden_size':8,'temporal_num_layers':1,'temporal_dropout':0.0,'temporal_learning_rate':.001,'temporal_batch_size':64,'temporal_epochs':1,'temporal_weight_decay':0.0,
    'policy_n_estimators':12,'policy_max_depth':4,'policy_min_samples_leaf':2,'policy_max_features':.7}
hfam='hybrid::gru::random_forest'; hm=make_model(CandidateSpec(hfam,'hybrid_purge',hp),cfg(6)); fit_model_indexed(hm,hfam,Xh,yh,np.arange(nh),cfg(6))
hev=dict(hm.temporal_internal_validation_); check(hev,6)
req(hm.stacking_schema_=='OOF_DIRECTION_STACK_V2_PURGED_INDEXED','hybrid remains leakage-safe OOF stacking')
req(int(hm.internal_label_horizon_bars_)==6,'hybrid encoder receives canonical label horizon')

# Small sample: horizon purge must fail closed, never silently use unpurged early validation.
Xs=rng.normal(size=(100,8)).astype(np.float32); ys=(np.arange(100)%3).astype(np.int64)
try:
    sm=make_model(CandidateSpec('gru','small',params('gru')),cfg(54)); fit_model_indexed(sm,'gru',Xs,ys,np.arange(len(Xs)),cfg(54)); rejected=False
except ValueError as exc:
    rejected='DL_INTERNAL_EARLYSTOP_PURGE_INSUFFICIENT' in str(exc)
req(rejected,'small-sample internal purge fails closed instead of leaking')

payload={'schema':'MAX_MTF_V201_LOCAL_TRAINING_SCIENTIFIC_EVIDENCE_V1','version':'2.0.1'}
if EVID.exists():
    try: payload.update(json.loads(EVID.read_text(encoding='utf-8')))
    except Exception: pass
payload.update({'schema':'MAX_MTF_V201_LOCAL_TRAINING_SCIENTIFIC_EVIDENCE_V1','version':'2.0.1','owner_runtime_claimed':False,
                'dl_internal_validation':{'effective_horizon':6,'families':family_evidence,'horizon_54_contiguous':h54_ev,'gapped_indices':gap_ev,'hybrid_temporal_encoder':hev,'small_sample_fail_closed':True}})
EVID.parent.mkdir(parents=True,exist_ok=True); EVID.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V201_DL_INTERNAL_EARLYSTOP_PURGE PASS')

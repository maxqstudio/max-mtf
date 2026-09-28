from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import torch
from models.models import CandidateSpec, make_model, fit_model_indexed, model_training_diagnostics
from research.temporal_research import TemporalClassifier

ROOT=Path(__file__).resolve().parents[1]; EVID=ROOT/'evidence/current/V201_TRAINING_SCIENTIFIC_EVIDENCE.json'
def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def configure_diverse_router(model):
    with torch.no_grad():
        for block in model.blocks:
            r=block.moe.router; r.weight.zero_(); r.bias.zero_()
            r.weight[0,0]=5.0; r.weight[1,1]=5.0; r.weight[2,0]=-5.0; r.weight[3,1]=-5.0

def task_gradient_health(model, x, y):
    model.zero_grad(set_to_none=True)
    p=model(x).clamp_min(1e-8); torch.nn.NLLLoss()(torch.log(p),y).backward()
    norms=TemporalClassifier._router_grad_norms(model)
    return norms, TemporalClassifier._router_gradient_health_from_samples([[v] for v in norms])

cfg={'models':{'gru_patience':2},'cpu_threads':1,'strategy_geometry':{'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':8},'split':{'purge_bars':8,'embargo_bars':8},'compute':{}}
rng=np.random.default_rng(2201); X=rng.normal(size=(280,8)).astype(np.float32); y=(np.arange(280)%3).astype(np.int64)
sp=CandidateSpec('transformer_moe','diag',{'sequence_length':12,'d_model':8,'num_layers':2,'attention_heads':2,'ffn_mult':2,'expert_ffn':16,'num_experts':4,'top_k':1,'router_temperature':1.0,'load_balance_coef':.01,'dropout':0.,'learning_rate':.001,'batch_size':64,'epochs':3,'weight_decay':0.})
m=make_model(sp,cfg); fit_model_indexed(m,'transformer_moe',X,y,np.arange(len(X)),cfg)
d=dict(m.routing_diagnostics_ or {}); blocks=list(d.get('blocks') or [])
shares=np.asarray(d.get('expert_dispatch_share'),float); soft=np.asarray(d.get('mean_soft_router_probability'),float)
req(d.get('diagnostic_weight_source')=='RESTORED_BEST_EARLYSTOP_CHECKPOINT' and d.get('diagnostics_recomputed_after_restore') is True and d.get('router_gradient_recomputed_after_restore') is True,'routing and per-block router-gradient diagnostics are recomputed after best-checkpoint restore')
req(int(d.get('best_checkpoint_epoch',-1))==int(m.train_report_.best_epoch),'routing diagnostics bind to restored best epoch')
req(d.get('checkpoint_router_signature')==m._router_parameter_signature(),'routing diagnostics bind to exact restored router parameters')
req(d.get('authority')=='PER_MOE_BLOCK' and d.get('per_block_authority') is True and d.get('aggregate_summary_authoritative') is False and len(blocks)==2,'per-block MoE routing is scientific authority; aggregate remains informational only')
for block_id,b in enumerate(blocks):
    ds=np.asarray(b.get('expert_dispatch_share'),float); spb=np.asarray(b.get('mean_soft_router_probability'),float)
    req(int(b.get('block_id',-1))==block_id and ds.shape==(4,) and np.isfinite(ds).all() and abs(float(ds.sum())-1.0)<1e-6,f'block {block_id} dispatch shares are valid')
    req(spb.shape==(4,) and np.isfinite(spb).all() and abs(float(spb.sum())-1.0)<1e-6,f'block {block_id} soft router probabilities are valid')
    req(math.isfinite(float(b.get('routing_entropy'))) and math.isfinite(float(b.get('dispatch_entropy'))),f'block {block_id} routing entropies are finite')
    req(abs(float(b.get('minimum_expert_share'))-float(ds.min()))<1e-12 and abs(float(b.get('maximum_expert_share'))-float(ds.max()))<1e-12,f'block {block_id} min/max shares match its own experts')
    req(0<=int(b.get('dead_expert_count'))<=4 and 0.0<=float(b.get('effective_expert_count'))<=4.000001 and 0.0<=float(b.get('effective_utilization'))<=1.000001,f'block {block_id} dead/effective expert diagnostics are bounded')
    req(b.get('router_gradient_status')=='PASS' and float(b.get('router_gradient_max',0))>1e-6 and float(b.get('router_gradient_mean',0))>0,f'block {block_id} carries independent production router-gradient health')
req(shares.shape==(4,) and abs(float(shares.sum())-1.0)<1e-6 and soft.shape==(4,) and abs(float(soft.sum())-1.0)<1e-6,'whole-model aggregate summaries remain valid informational telemetry')
req(d.get('expert_identity')=='LATENT_LEARNED_EXPERTS','diagnostics do not claim regime-supervised expert identities')
exposed=model_training_diagnostics(m)
req((exposed.get('routing_diagnostics') or {}).get('checkpoint_router_signature')==d.get('checkpoint_router_signature'),'production evidence adapter exposes restored-checkpoint per-block routing diagnostics')
registry=json.loads((ROOT/'config/models/model_registry.json').read_text(encoding='utf-8'))['families']['transformer_moe']
req(registry.get('expert_identity')=='LATENT_LEARNED_EXPERTS_0_TO_N_MINUS_1' and registry.get('strategy_expert_prior_semantics')=='DESCRIPTIVE_PRIOR_ONLY_NOT_SUPERVISED_EXPERT_IDENTITY','active registry states latent expert identity truthfully')

# Healthy deterministic two-block fixture: every block routes to all experts and has non-trivial task gradient.
healthy=TemporalClassifier(architecture='transformer_moe',sequence_length=12,d_model=8,hidden_size=8,num_layers=2,attention_heads=2,ffn_mult=2,expert_ffn=16,num_experts=4,top_k=1,dropout=0.0,epochs=1,batch_size=64,threads=1)
healthy.feature_mean_=np.zeros(8,dtype=np.float32); healthy.feature_std_=np.ones(8,dtype=np.float32); healthy.model_=healthy._make_model(8); configure_diverse_router(healthy.model_)
probe=rng.normal(size=(256,12,8)).astype(np.float32); tx=torch.from_numpy(probe[:64]); ty=torch.arange(64)%3
healthy_norms,healthy_gh=task_gradient_health(healthy.model_,tx,ty)
healthy_diag=healthy._routing_diagnostics_from_sequences(probe,best_epoch=1,router_gradient_health=healthy_gh)
req(healthy_gh.get('status')=='PASS' and all(v>1e-6 for v in healthy_norms),'normal two-block fixture has non-trivial task gradient in every router')
req(healthy_diag.get('routing_health_status')=='PASS' and all(b.get('routing_health_status')=='PASS' and int(b.get('dead_expert_count'))==0 for b in healthy_diag['blocks']),'normal healthy multi-layer fixture can PASS only when every block is healthy')

# Adversarial routing fixture: block 0 collapsed, block 1 healthy. Aggregate has no dead expert, but overall authority must reject PASS.
collapsed=TemporalClassifier(architecture='transformer_moe',sequence_length=12,d_model=8,hidden_size=8,num_layers=2,attention_heads=2,ffn_mult=2,expert_ffn=16,num_experts=4,top_k=1,dropout=0.0,epochs=1,batch_size=64,threads=1)
collapsed.feature_mean_=np.zeros(8,dtype=np.float32); collapsed.feature_std_=np.ones(8,dtype=np.float32); collapsed.model_=collapsed._make_model(8)
with torch.no_grad():
    b0=collapsed.model_.blocks[0].moe.router; b0.weight.zero_(); b0.bias.copy_(torch.tensor([80.0,-80.0,-80.0,-80.0]))
    b1=collapsed.model_.blocks[1].moe.router; b1.weight.zero_(); b1.bias.zero_(); b1.weight[0,0]=5.0; b1.weight[1,1]=5.0; b1.weight[2,0]=-5.0; b1.weight[3,1]=-5.0
collapse_diag=collapsed._routing_diagnostics_from_sequences(probe,best_epoch=1)
req(collapse_diag['blocks'][0].get('obvious_single_expert_collapse') is True and int(collapse_diag['blocks'][0].get('dead_expert_count'))==3,'block 0 deterministic single-expert collapse is detected independently')
req(collapse_diag['blocks'][1].get('routing_distribution_status')=='PASS' and int(collapse_diag['blocks'][1].get('dead_expert_count'))==0,'block 1 remains independently healthy in collapse fixture')
req(int(collapse_diag.get('dead_expert_count'))==0 and collapse_diag.get('routing_health_status')!='PASS','healthy block cannot hide collapsed block even when aggregate utilization has zero dead experts')

# Adversarial gradient fixture on same model: block 0 gradient zero, block 1 healthy, aggregate norm > 0.
bad_norms,bad_gh=task_gradient_health(collapsed.model_,tx,ty)
bad_diag=TemporalClassifier._attach_router_gradient_health(collapse_diag,bad_gh)
req(bad_norms[0]<=1e-12 and bad_norms[1]>1e-6 and TemporalClassifier._router_grad_norm(collapsed.model_)>1e-6,'gradient fixture reproduces dead block hidden by healthy whole-model aggregate norm')
req(bad_gh.get('status')!='PASS' and 0 in bad_gh.get('failed_block_ids',[]) and bad_diag.get('routing_health_status')!='PASS' and bad_diag['blocks'][0].get('router_gradient_status')!='PASS' and bad_diag['blocks'][1].get('router_gradient_status')=='PASS','per-block gradient authority prevents healthy router from hiding dead router')

# Every latent expert remains reachable in each independent block implementation.
reachable=[]
reach=TemporalClassifier(architecture='transformer_moe',sequence_length=12,d_model=8,hidden_size=8,num_layers=2,attention_heads=2,ffn_mult=2,expert_ffn=16,num_experts=4,top_k=1,dropout=0.0,epochs=1,batch_size=32,threads=1)
reach.feature_mean_=np.zeros(8,dtype=np.float32); reach.feature_std_=np.ones(8,dtype=np.float32); reach.model_=reach._make_model(8)
small_probe=rng.normal(size=(16,12,8)).astype(np.float32)
for block_id in range(2):
    for expert_id in range(4):
        with torch.no_grad():
            for j,block in enumerate(reach.model_.blocks):
                block.moe.router.weight.zero_(); block.moe.router.bias.fill_(-50.0); block.moe.router.bias[(expert_id if j==block_id else 0)]=50.0
        rd=reach._routing_diagnostics_from_sequences(small_probe,best_epoch=1)
        bs=np.asarray(rd['blocks'][block_id]['expert_dispatch_share'],float)
        reachable.append(bool(np.argmax(bs)==expert_id and float(bs[expert_id])>0.999999))
req(all(reachable),'every latent expert is deterministically reachable in every independent MoE block')

payload={}
if EVID.exists():
    try: payload=json.loads(EVID.read_text(encoding='utf-8'))
    except Exception: payload={}
payload.update({'schema':'MAX_MTF_V201_LOCAL_TRAINING_SCIENTIFIC_EVIDENCE_V1','version':'2.0.1','owner_runtime_claimed':False})
payload['moe_routing_diagnostics']=d
payload['moe_multilayer_authority']={'healthy_fixture':{'router_norms':healthy_norms,'routing_health_status':healthy_diag['routing_health_status']},'collapsed_block_fixture':{'aggregate_dead_expert_count':int(collapse_diag['dead_expert_count']),'overall_routing_health_status':collapse_diag['routing_health_status'],'per_block':collapse_diag['blocks']},'dead_router_gradient_fixture':{'per_block_gradient_norms':bad_norms,'whole_model_aggregate_norm':TemporalClassifier._router_grad_norm(collapsed.model_),'gradient_health':bad_gh,'overall_routing_health_status':bad_diag['routing_health_status']},'all_experts_reachable_per_block':bool(all(reachable))}
payload['research_evidence_exposure']={'authority':'MODEL_TRAINING_DIAGNOSTICS_FROM_FITTED_PRODUCTION_MODEL','surfaces':['WFA_FOLD','CPCV_SPLIT','TOURNAMENT_CANDIDATE','FRESH_FORWARD_CANDIDATE']}
EVID.parent.mkdir(parents=True,exist_ok=True); EVID.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V201_MOE_ROUTING_DIAGNOSTICS PASS')

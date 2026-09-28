from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import torch
from research.temporal_research import TemporalNet, TemporalClassifier
from models.models import CandidateSpec, make_model, fit_model_indexed

ROOT=Path(__file__).resolve().parents[1]; EVID=ROOT/'evidence/current/V201_TRAINING_SCIENTIFIC_EVIDENCE.json'
def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)
def router_grad_norm(model):
    vals=TemporalClassifier._router_grad_norms(model)
    if any(not math.isfinite(v) for v in vals): return float('nan')
    return math.sqrt(sum(v*v for v in vals)) if vals else 0.0

torch.manual_seed(1201); np.random.seed(1201)
net=TemporalNet(architecture='transformer_moe',n_features=8,n_classes=3,d_model=8,hidden_size=8,num_layers=1,attention_heads=2,ffn_mult=2,expert_ffn=16,num_experts=4,top_k=1,dropout=0.0,sequence_length=12,mean=np.zeros(8,np.float32),std=np.ones(8,np.float32))
x=torch.randn(32,12,8); y=torch.arange(32)%3
# Task-only: proves top-1 selected gate magnitude remains differentiable.
net.zero_grad(set_to_none=True); p=net(x).clamp_min(1e-8); task=torch.nn.NLLLoss()(torch.log(p),y); task.backward(); task_grad=router_grad_norm(net)
req(math.isfinite(task_grad) and task_grad>1e-6,f'top_k=1 task objective produces non-trivial router gradient ({task_grad:.6g})')
# Auxiliary-only: Switch-style hard-load x mean-soft-prob objective must also train router.
net.zero_grad(set_to_none=True); net(x); aux=net.router_balance_loss(); aux.backward(); aux_grad=router_grad_norm(net)
req(math.isfinite(aux_grad) and aux_grad>1e-6,f'top_k=1 balance objective produces non-trivial router gradient ({aux_grad:.6g})')
# Top-k > 1 must also retain gate-magnitude task gradients (no selected-gate renormalization cancellation).
torch.manual_seed(1203)
net2=TemporalNet(architecture='transformer_moe',n_features=8,n_classes=3,d_model=8,hidden_size=8,num_layers=1,attention_heads=2,ffn_mult=2,expert_ffn=16,num_experts=4,top_k=2,dropout=0.0,sequence_length=12,mean=np.zeros(8,np.float32),std=np.ones(8,np.float32))
net2.zero_grad(set_to_none=True); p2=net2(x).clamp_min(1e-8); task2=torch.nn.NLLLoss()(torch.log(p2),y); task2.backward(); top2_grad=router_grad_norm(net2)
req(math.isfinite(top2_grad) and top2_grad>1e-6,f'top_k=2 task objective retains non-trivial selected-gate router gradient ({top2_grad:.6g})')

# Adversarial multi-layer fixture: aggregate norm is healthy while block 0 is saturated/dead.
torch.manual_seed(1204)
net_bad=TemporalNet(architecture='transformer_moe',n_features=8,n_classes=3,d_model=8,hidden_size=8,num_layers=2,attention_heads=2,ffn_mult=2,expert_ffn=16,num_experts=4,top_k=1,dropout=0.0,sequence_length=12,mean=np.zeros(8,np.float32),std=np.ones(8,np.float32))
with torch.no_grad():
    net_bad.blocks[0].moe.router.weight.zero_(); net_bad.blocks[0].moe.router.bias.copy_(torch.tensor([80.0,-80.0,-80.0,-80.0]))
net_bad.zero_grad(set_to_none=True); pb=net_bad(x).clamp_min(1e-8); lb=torch.nn.NLLLoss()(torch.log(pb),y); lb.backward()
bad_block_norms=TemporalClassifier._router_grad_norms(net_bad); bad_aggregate=TemporalClassifier._router_grad_norm(net_bad)
bad_health=TemporalClassifier._router_gradient_health_from_samples([[v] for v in bad_block_norms])
req(bad_block_norms[0]<=1e-12 and bad_block_norms[1]>1e-6 and bad_aggregate>1e-6,'adversarial fixture reproduces dead block hidden by healthy aggregate router norm')
req(bad_health.get('status')!='PASS' and 0 in bad_health.get('failed_block_ids',[]) and bad_health['per_block'][0]['router_gradient_status']!='PASS' and bad_health['per_block'][1]['router_gradient_status']=='PASS','per-block router-gradient authority rejects dead block even when whole-model aggregate norm is non-trivial')

# Exercise actual TemporalClassifier training with multiple MoE blocks.
cfg={'models':{'gru_patience':1},'cpu_threads':1,'strategy_geometry':{'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':8},'split':{'purge_bars':8,'embargo_bars':8},'compute':{}}
rng=np.random.default_rng(1202); X=rng.normal(size=(240,8)).astype(np.float32); yy=(np.arange(240)%3).astype(np.int64)
sp=CandidateSpec('transformer_moe','top1_train',{'sequence_length':12,'d_model':8,'num_layers':2,'attention_heads':2,'ffn_mult':2,'expert_ffn':16,'num_experts':4,'top_k':1,'router_temperature':1.0,'load_balance_coef':.01,'dropout':0.,'learning_rate':.001,'batch_size':64,'epochs':2,'weight_decay':0.})
m=make_model(sp,cfg); fit_model_indexed(m,'transformer_moe',X,yy,np.arange(len(X)),cfg)
h=dict(m.router_gradient_health_ or {}); per=list(h.get('per_block') or [])
req(h.get('authority')=='PER_MOE_BLOCK' and int(h.get('num_blocks',0))==2 and h.get('gradient_weight_source')=='RESTORED_BEST_EARLYSTOP_CHECKPOINT_DETERMINISTIC_OBJECTIVE_PROBE','production training records restored-checkpoint router-gradient authority independently for every MoE block')
req(h.get('status')=='PASS' and len(per)==2 and all(r.get('router_gradient_status')=='PASS' and float(r.get('router_gradient_max',0))>1e-6 for r in per),'normal multi-layer production training has finite non-trivial router gradients in every block')

payload={}
if EVID.exists():
    try: payload=json.loads(EVID.read_text(encoding='utf-8'))
    except Exception: payload={}
payload.update({'schema':'MAX_MTF_V201_LOCAL_TRAINING_SCIENTIFIC_EVIDENCE_V1','version':'2.0.1','owner_runtime_claimed':False})
payload['moe_router_gradient']={'num_experts':4,'top_k':1,'task_router_gradient_norm':task_grad,'auxiliary_balance_gradient_norm':aux_grad,'top2_task_router_gradient_norm':top2_grad,'adversarial_multilayer':{'per_block_gradient_norms':bad_block_norms,'whole_model_aggregate_norm':bad_aggregate,'health':bad_health},'training_gradient_health':h}
EVID.parent.mkdir(parents=True,exist_ok=True); EVID.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V201_MOE_TOP1_ROUTER_GRADIENT PASS')

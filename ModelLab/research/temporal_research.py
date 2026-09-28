from __future__ import annotations

import copy
import hashlib
import math
from dataclasses import dataclass

import numpy as np

from research.gru_research import sequence_tensor, sequence_tensor_with_context, sequence_tensor_for_indices
from core.temporal_index import sorted_unique_indices, purged_internal_earlystop_split

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except Exception as exc:  # pragma: no cover
    raise RuntimeError("Temporal research families require PyTorch") from exc


class _CausalConvBlock(nn.Module):
    def __init__(self, channels: int, kernel_size: int, dilation: int, dropout: float):
        super().__init__()
        self.pad = int((kernel_size - 1) * dilation)
        self.conv1 = nn.Conv1d(channels, channels, kernel_size, dilation=dilation)
        self.conv2 = nn.Conv1d(channels, channels, kernel_size, dilation=dilation)
        self.dropout = nn.Dropout(float(dropout))
        self.norm1 = nn.BatchNorm1d(channels)
        self.norm2 = nn.BatchNorm1d(channels)

    def forward(self, x):
        y = self.conv1(F.pad(x, (self.pad, 0)))
        y = self.dropout(torch.relu(self.norm1(y)))
        y = self.conv2(F.pad(y, (self.pad, 0)))
        y = self.dropout(torch.relu(self.norm2(y)))
        return torch.relu(x + y)


class _TinyCausalAttention(nn.Module):
    def __init__(self, d_model: int, heads: int, dropout: float, max_len: int):
        super().__init__()
        self.d_model = int(d_model)
        self.heads = int(heads)
        self.head_dim = self.d_model // self.heads
        self.qkv = nn.Linear(self.d_model, self.d_model * 3)
        self.proj = nn.Linear(self.d_model, self.d_model)
        self.dropout = nn.Dropout(float(dropout))
        mask = torch.triu(torch.ones(max_len, max_len, dtype=torch.bool), diagonal=1)
        self.register_buffer("causal_mask", mask, persistent=False)

    def forward(self, x):
        b, t, d = x.shape
        qkv = self.qkv(x).view(b, t, 3, self.heads, self.head_dim).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(float(self.head_dim))
        mask = self.causal_mask[:t, :t].view(1, 1, t, t)
        scores = scores.masked_fill(mask, -10000.0)
        attn = torch.softmax(scores, dim=-1)
        attn = self.dropout(attn)
        y = torch.matmul(attn, v).transpose(1, 2).contiguous().view(b, t, d)
        return self.proj(y)




class _FullAttention(nn.Module):
    """Standard self-attention without a temporal causal mask.

    Used only when token order is not time order (iTransformer feature tokens).
    The input window itself remains strictly historical, so this does not introduce
    future leakage.
    """
    def __init__(self, d_model: int, heads: int, dropout: float):
        super().__init__()
        self.d_model=int(d_model); self.heads=int(heads); self.head_dim=self.d_model//self.heads
        self.qkv=nn.Linear(self.d_model,self.d_model*3)
        self.proj=nn.Linear(self.d_model,self.d_model)
        self.dropout=nn.Dropout(float(dropout))

    def forward(self,x):
        b,t,d=x.shape
        qkv=self.qkv(x).view(b,t,3,self.heads,self.head_dim).permute(2,0,3,1,4)
        q,k,v=qkv[0],qkv[1],qkv[2]
        scores=torch.matmul(q,k.transpose(-2,-1))/math.sqrt(float(self.head_dim))
        attn=self.dropout(torch.softmax(scores,dim=-1))
        y=torch.matmul(attn,v).transpose(1,2).contiguous().view(b,t,d)
        return self.proj(y)


class _FullTransformerBlock(nn.Module):
    def __init__(self,d_model:int,heads:int,ffn_mult:int,dropout:float):
        super().__init__()
        self.norm1=nn.LayerNorm(d_model); self.attn=_FullAttention(d_model,heads,dropout)
        self.norm2=nn.LayerNorm(d_model)
        self.ff=nn.Sequential(
            nn.Linear(d_model,d_model*int(ffn_mult)),nn.GELU(),nn.Dropout(dropout),
            nn.Linear(d_model*int(ffn_mult),d_model),nn.Dropout(dropout),
        )
    def forward(self,x):
        x=x+self.attn(self.norm1(x))
        return x+self.ff(self.norm2(x))

class _TinyTransformerBlock(nn.Module):
    def __init__(self, d_model: int, heads: int, ffn_mult: int, dropout: float, max_len: int):
        super().__init__()
        self.norm1 = nn.LayerNorm(d_model)
        self.attn = _TinyCausalAttention(d_model, heads, dropout, max_len)
        self.norm2 = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(
            nn.Linear(d_model, d_model * int(ffn_mult)), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(d_model * int(ffn_mult), d_model), nn.Dropout(dropout),
        )

    def forward(self, x):
        x = x + self.attn(self.norm1(x))
        x = x + self.ff(self.norm2(x))
        return x




class _MoEFeedForward(nn.Module):
    """Top-k latent FFN experts with differentiable sparse gate magnitude.

    All expert outputs are materialized for ONNX portability. Selection is hard top-k,
    while selected softmax gate magnitudes remain in the task path. In particular,
    top_k=1 is NOT renormalized to one; the selected probability remains
    differentiable so the task objective can train the router. Expert identities are
    latent learned experts, not supervised TREND/RANGE/TRANSITION/SHOCK labels.
    """
    def __init__(self, d_model: int, expert_ffn: int, num_experts: int, top_k: int, dropout: float, router_temperature: float = 1.0):
        super().__init__()
        self.num_experts=max(2,int(num_experts)); self.top_k=max(1,min(int(top_k),self.num_experts))
        self.router_temperature=max(0.05,float(router_temperature))
        self.router=nn.Linear(int(d_model),self.num_experts)
        self.experts=nn.ModuleList([
            nn.Sequential(
                nn.Linear(int(d_model),int(expert_ffn)), nn.GELU(), nn.Dropout(float(dropout)),
                nn.Linear(int(expert_ffn),int(d_model)), nn.Dropout(float(dropout)),
            ) for _ in range(self.num_experts)
        ])
        self._last_balance=None; self._last_dispatch_share=None; self._last_soft_probability=None; self._last_entropy=None

    def forward(self,x):
        logits=self.router(x)/self.router_temperature
        probs=torch.softmax(logits,dim=-1)
        _topv,topi=torch.topk(probs,k=self.top_k,dim=-1)
        mask=F.one_hot(topi,num_classes=self.num_experts).to(probs.dtype).sum(dim=-2).clamp_max(1.0)
        # Do not renormalize selected gates. Renormalizing a single selected gate makes
        # p_selected / p_selected == 1 and destroys useful task-loss router magnitude gradient.
        weights=probs*mask
        expert_out=torch.stack([expert(x) for expert in self.experts],dim=-2)
        out=(expert_out*weights.unsqueeze(-1)).sum(dim=-2)
        # Switch-style differentiable balancing: hard dispatch/load is treated as the
        # realized routing observation; mean raw soft probability supplies gradient.
        dispatch_share=mask.mean(dim=(0,1))/float(self.top_k)
        soft_probability=probs.mean(dim=(0,1))
        balance=float(self.num_experts)*torch.sum(dispatch_share.detach()*soft_probability)
        entropy=-(probs.clamp_min(1e-12)*torch.log(probs.clamp_min(1e-12))).sum(dim=-1).mean()
        self._last_dispatch_share=dispatch_share; self._last_soft_probability=soft_probability
        self._last_balance=balance; self._last_entropy=entropy
        return out

    def balance_loss(self):
        if self._last_balance is None:
            return torch.tensor(0.0,device=self.router.weight.device)
        return self._last_balance

    def usage(self):
        if self._last_dispatch_share is None:
            return None
        return self._last_dispatch_share.detach()

    def routing_snapshot(self):
        if self._last_dispatch_share is None or self._last_soft_probability is None:
            return None
        return {
            'dispatch_share':self._last_dispatch_share.detach(),
            'mean_soft_probability':self._last_soft_probability.detach(),
            'routing_entropy':None if self._last_entropy is None else self._last_entropy.detach(),
        }


class _TinyTransformerMoEBlock(nn.Module):
    def __init__(self,d_model:int,heads:int,expert_ffn:int,num_experts:int,top_k:int,dropout:float,max_len:int,router_temperature:float=1.0):
        super().__init__()
        self.norm1=nn.LayerNorm(d_model)
        self.attn=_TinyCausalAttention(d_model,heads,dropout,max_len)
        self.norm2=nn.LayerNorm(d_model)
        self.moe=_MoEFeedForward(d_model,expert_ffn,num_experts,top_k,dropout,router_temperature)

    def forward(self,x):
        x=x+self.attn(self.norm1(x))
        x=x+self.moe(self.norm2(x))
        return x


class TemporalNet(nn.Module):
    """Causal temporal classifier supporting recurrent, convolutional and Transformer-family research models."""

    def __init__(self, *, architecture: str, n_features: int, n_classes: int,
                 hidden_size: int = 64, num_layers: int = 1, dropout: float = 0.1,
                 tcn_channels: int | None = None, tcn_blocks: int = 3, kernel_size: int = 3,
                 d_model: int | None = None, attention_heads: int = 4, ffn_mult: int = 2,
                 expert_ffn: int | None = None, num_experts: int = 4, top_k: int = 1,
                 router_temperature: float = 1.0, load_balance_coef: float = 0.01,
                 patch_len: int = 16, patch_stride: int = 8, tft_lstm_layers: int = 1,
                 sequence_length: int = 128, mean=None, std=None):
        super().__init__()
        self.architecture = str(architecture).lower()
        self.n_classes = int(n_classes)
        self.register_buffer("feature_mean", torch.as_tensor(mean, dtype=torch.float32).view(1, 1, -1))
        self.register_buffer("feature_std", torch.as_tensor(std, dtype=torch.float32).view(1, 1, -1))
        if self.architecture == "gru":
            self.core = nn.GRU(n_features, hidden_size, num_layers=num_layers,
                               dropout=dropout if num_layers > 1 else 0.0, batch_first=True)
            self.head = nn.Linear(hidden_size, n_classes)
            self.mode = "rnn"
        elif self.architecture == "lstm":
            self.core = nn.LSTM(n_features, hidden_size, num_layers=num_layers,
                                dropout=dropout if num_layers > 1 else 0.0, batch_first=True)
            self.head = nn.Linear(hidden_size, n_classes)
            self.mode = "rnn"
        elif self.architecture == "tcn":
            ch = int(tcn_channels or hidden_size)
            self.input_proj = nn.Conv1d(n_features, ch, 1)
            self.blocks = nn.ModuleList([
                _CausalConvBlock(ch, int(kernel_size), 2 ** i, dropout) for i in range(int(tcn_blocks))
            ])
            self.head = nn.Linear(ch, n_classes)
            self.mode = "tcn"
        elif self.architecture in {"transformer","transformer_moe","patchtst","itransformer","tft"}:
            dm = int(d_model or hidden_size)
            heads = max(1, int(attention_heads))
            if dm % heads != 0:
                divisors = [h for h in range(min(8, dm), 0, -1) if dm % h == 0]
                heads = divisors[0] if divisors else 1
            self.load_balance_coef=0.0
            if self.architecture == "patchtst":
                # CPMF PatchTST adaptation: chronological multivariate patches become
                # causal Transformer tokens.  The last patch always ends at the current
                # bar, avoiding future leakage and preserving the fixed CP32 ONNX input.
                self.patch_len=max(2,min(int(patch_len),int(sequence_length)))
                self.patch_stride=max(1,min(int(patch_stride),self.patch_len))
                self.patch_count=1+max(0,(int(sequence_length)-self.patch_len)//self.patch_stride)
                self.patch_span=self.patch_len+(self.patch_count-1)*self.patch_stride
                self.patch_proj=nn.Linear(int(n_features)*self.patch_len,dm)
                self.position=nn.Parameter(torch.zeros(1,self.patch_count,dm)); nn.init.normal_(self.position,std=0.02)
                self.blocks=nn.ModuleList([_TinyTransformerBlock(dm,heads,int(ffn_mult),dropout,self.patch_count) for _ in range(int(num_layers))])
                self.norm=nn.LayerNorm(dm); self.head=nn.Linear(dm,n_classes); self.mode="patchtst"
            elif self.architecture == "itransformer":
                # iTransformer-style inverted tokenization: each CP32 variable is a token
                # whose embedding summarizes only the historical lookback window.
                self.inverted_proj=nn.Linear(int(sequence_length),dm)
                self.variable_position=nn.Parameter(torch.zeros(1,int(n_features),dm)); nn.init.normal_(self.variable_position,std=0.02)
                self.blocks=nn.ModuleList([_FullTransformerBlock(dm,heads,int(ffn_mult),dropout) for _ in range(int(num_layers))])
                self.norm=nn.LayerNorm(dm); self.head=nn.Linear(dm,n_classes); self.mode="itransformer"
            elif self.architecture == "tft":
                # Observed-covariate TFT adaptation for CP32.  CPMF has no known-future
                # or static covariate contract, so variable selection + recurrent local
                # processing + causal attention are used without fabricating covariates.
                self.variable_gate=nn.Linear(int(n_features),int(n_features))
                self.input_proj=nn.Linear(int(n_features),dm)
                lstm_layers=max(1,int(tft_lstm_layers))
                self.local_lstm=nn.LSTM(dm,dm,num_layers=lstm_layers,batch_first=True,dropout=dropout if lstm_layers>1 else 0.0)
                self.local_gate=nn.Linear(dm,dm)
                self.blocks=nn.ModuleList([_TinyTransformerBlock(dm,heads,int(ffn_mult),dropout,int(sequence_length)) for _ in range(max(1,int(num_layers)))])
                self.norm=nn.LayerNorm(dm); self.head=nn.Linear(dm,n_classes); self.mode="tft"
            else:
                self.input_proj = nn.Linear(n_features, dm)
                self.position = nn.Parameter(torch.zeros(1, int(sequence_length), dm))
                nn.init.normal_(self.position, std=0.02)
                if self.architecture == "transformer_moe":
                    ef=int(expert_ffn or max(dm*2,64))
                    self.blocks=nn.ModuleList([
                        _TinyTransformerMoEBlock(dm,heads,ef,int(num_experts),int(top_k),dropout,int(sequence_length),float(router_temperature))
                        for _ in range(int(num_layers))
                    ])
                    self.load_balance_coef=float(load_balance_coef)
                    self.mode="transformer_moe"
                else:
                    self.blocks = nn.ModuleList([
                        _TinyTransformerBlock(dm, heads, int(ffn_mult), dropout, int(sequence_length))
                        for _ in range(int(num_layers))
                    ])
                    self.mode = "transformer"
                self.norm = nn.LayerNorm(dm)
                self.head = nn.Linear(dm, n_classes)
        else:
            raise ValueError(f"Unsupported temporal architecture: {architecture}")

    def forward(self, x):
        x = (x - self.feature_mean) / self.feature_std
        if self.mode == "rnn":
            y, _ = self.core(x)
            z = y[:, -1, :]
        elif self.mode == "tcn":
            y = self.input_proj(x.transpose(1, 2))
            for block in self.blocks:
                y = block(y)
            z = y[:, :, -1]
        elif self.mode == "patchtst":
            xt=x[:, -self.patch_span:, :]
            patches=torch.stack([
                xt[:, i*self.patch_stride:i*self.patch_stride+self.patch_len, :].flatten(1)
                for i in range(self.patch_count)
            ],dim=1)
            y=self.patch_proj(patches)+self.position[:, :patches.shape[1], :]
            for block in self.blocks: y=block(y)
            z=self.norm(y)[:, -1, :]
        elif self.mode == "itransformer":
            y=self.inverted_proj(x.transpose(1,2))+self.variable_position
            for block in self.blocks: y=block(y)
            z=self.norm(y).mean(dim=1)
        elif self.mode == "tft":
            weights=torch.softmax(self.variable_gate(x),dim=-1)
            base=self.input_proj(x*weights)
            local,_=self.local_lstm(base)
            y=base+torch.sigmoid(self.local_gate(local))*local
            for block in self.blocks: y=block(y)
            z=self.norm(y)[:, -1, :]
        else:
            y = self.input_proj(x) + self.position[:, : x.shape[1], :]
            for block in self.blocks:
                y = block(y)
            z = self.norm(y)[:, -1, :]
        return torch.softmax(self.head(z), dim=1)

    def router_balance_loss(self):
        if self.mode != "transformer_moe":
            return torch.tensor(0.0,device=self.head.weight.device)
        vals=[b.moe.balance_loss() for b in self.blocks]
        return torch.stack(vals).mean() if vals else torch.tensor(0.0,device=self.head.weight.device)

    def expert_usage(self):
        if self.mode != "transformer_moe":
            return None
        vals=[b.moe.usage() for b in self.blocks if b.moe.usage() is not None]
        if not vals:
            return None
        return torch.stack(vals).mean(dim=0)

    def routing_snapshots(self):
        if self.mode != "transformer_moe":
            return []
        out=[]
        for block in self.blocks:
            snap=block.moe.routing_snapshot()
            if snap is not None: out.append(snap)
        return out


@dataclass
class TemporalTrainReport:
    architecture: str
    epochs_ran: int
    best_epoch: int
    best_val_loss: float | None
    train_rows: int
    val_rows: int
    internal_validation: dict | None = None
    routing_diagnostics: dict | None = None


class TemporalClassifier:
    """sklearn-like causal sequence classifier for the registered PyTorch temporal families."""

    def __init__(self, *, architecture="gru", sequence_length=128, hidden_size=64, num_layers=1,
                 dropout=0.1, learning_rate=0.001, batch_size=128, epochs=30, weight_decay=0.0001,
                 patience=5, random_state=42, threads=4, device="cpu", compute_backend="CPU",
                 tcn_channels=None, tcn_blocks=3, kernel_size=3, d_model=None, attention_heads=4,
                 ffn_mult=2, expert_ffn=None, num_experts=4, top_k=1, router_temperature=1.0,
                 load_balance_coef=0.01, patch_len=16, patch_stride=8, tft_lstm_layers=1, n_classes=3):
        self.architecture = str(architecture).lower(); self.sequence_length = int(sequence_length)
        self.hidden_size = int(hidden_size); self.num_layers = int(num_layers); self.dropout = float(dropout)
        self.learning_rate = float(learning_rate); self.batch_size = int(batch_size); self.epochs = int(epochs)
        self.weight_decay = float(weight_decay); self.patience = int(patience); self.random_state = int(random_state)
        self.threads = int(threads); self.device_name = str(device or "cpu"); self.compute_backend = str(compute_backend or "CPU")
        self.device = torch.device(self.device_name); self.tcn_channels = int(tcn_channels or hidden_size)
        self.tcn_blocks = int(tcn_blocks); self.kernel_size = int(kernel_size); self.d_model = int(d_model or hidden_size)
        self.attention_heads = int(attention_heads); self.ffn_mult = int(ffn_mult); self.n_classes = int(n_classes)
        self.expert_ffn=int(expert_ffn or max(self.d_model*2,64)); self.num_experts=max(2,int(num_experts)); self.top_k=max(1,min(int(top_k),self.num_experts))
        self.router_temperature=max(0.05,float(router_temperature)); self.load_balance_coef=max(0.0,float(load_balance_coef))
        self.patch_len=max(2,min(int(patch_len),self.sequence_length)); self.patch_stride=max(1,min(int(patch_stride),self.patch_len))
        self.tft_lstm_layers=max(1,int(tft_lstm_layers))
        self.classes_ = np.arange(self.n_classes, dtype=np.int64)
        self.model_ = None; self.feature_mean_ = None; self.feature_std_ = None; self.train_report_ = None; self.internal_validation_ = None; self.routing_diagnostics_ = None; self.router_gradient_health_ = None

    def _seed(self):
        torch.manual_seed(self.random_state); np.random.seed(self.random_state)
        try: torch.set_num_threads(max(1, self.threads))
        except Exception: pass

    def _make_model(self, n_features: int):
        return TemporalNet(
            architecture=self.architecture, n_features=n_features, n_classes=self.n_classes,
            hidden_size=self.hidden_size, num_layers=self.num_layers, dropout=self.dropout,
            tcn_channels=self.tcn_channels, tcn_blocks=self.tcn_blocks, kernel_size=self.kernel_size,
            d_model=self.d_model, attention_heads=self.attention_heads, ffn_mult=self.ffn_mult,
            expert_ffn=self.expert_ffn, num_experts=self.num_experts, top_k=self.top_k,
            router_temperature=self.router_temperature, load_balance_coef=self.load_balance_coef,
            patch_len=self.patch_len, patch_stride=self.patch_stride, tft_lstm_layers=self.tft_lstm_layers,
            sequence_length=self.sequence_length, mean=self.feature_mean_, std=self.feature_std_,
        ).to(self.device)

    def _router_parameter_signature(self):
        if self.model_ is None or getattr(self.model_,'mode',None)!='transformer_moe': return None
        h=hashlib.sha256()
        for block in self.model_.blocks:
            for name,p in block.moe.router.named_parameters():
                h.update(name.encode('utf-8')); h.update(b'\0'); h.update(p.detach().cpu().contiguous().numpy().tobytes())
        return h.hexdigest()

    @staticmethod
    def _router_grad_norms(model):
        """Return one router gradient norm per independent MoE block.

        Each Transformer-MoE block owns a different router.  Scientific health must
        therefore be evaluated per block; summing all routers can let a healthy block
        hide a dead/saturated router in another block.
        """
        if model is None or getattr(model,'mode',None)!='transformer_moe':
            return []
        out=[]
        for block in model.blocks:
            sq=0.0; seen=False; finite=True
            for param in block.moe.router.parameters():
                if param.grad is None:
                    continue
                seen=True
                term=float(torch.sum(param.grad.detach()*param.grad.detach()).item())
                if not math.isfinite(term):
                    finite=False; break
                sq += term
            out.append(float(math.sqrt(sq)) if seen and finite else (0.0 if not seen else float('nan')))
        return out

    @staticmethod
    def _router_grad_norm(model):
        """Compatibility whole-model norm; never use this as MoE health authority."""
        vals=TemporalClassifier._router_grad_norms(model)
        if any(not math.isfinite(v) for v in vals):
            return float('nan')
        return float(math.sqrt(sum(v*v for v in vals))) if vals else 0.0

    @staticmethod
    def _router_gradient_health_from_samples(samples_by_block):
        per_block=[]; all_finite=[]
        for block_id, samples in enumerate(samples_by_block or []):
            vals=[float(v) for v in samples]
            finite=[v for v in vals if math.isfinite(v)]
            if len(finite)!=len(vals):
                status='FAIL_NONFINITE_ROUTER_GRADIENT'
            elif not finite or max(finite)<=1e-12:
                status='FAIL_ZERO_ROUTER_GRADIENT'
            else:
                status='PASS'
            per_block.append({
                'block_id':int(block_id),'samples':int(len(vals)),'finite_samples':int(len(finite)),
                'router_gradient_max':float(max(finite) if finite else 0.0),
                'router_gradient_mean':float(np.mean(finite) if finite else 0.0),
                'router_gradient_status':status,
            })
            all_finite.extend(finite)
        failed=[int(row['block_id']) for row in per_block if row['router_gradient_status']!='PASS']
        return {
            'schema':'MAX_MOE_ROUTER_GRADIENT_HEALTH_V2','authority':'PER_MOE_BLOCK',
            'num_blocks':int(len(per_block)),'samples':int(sum(row['samples'] for row in per_block)),
            'finite_samples':int(sum(row['finite_samples'] for row in per_block)),
            'maximum_gradient_norm':float(max(all_finite) if all_finite else 0.0),
            'mean_gradient_norm':float(np.mean(all_finite) if all_finite else 0.0),
            'failed_block_ids':failed,'status':('PASS' if per_block and not failed else 'FAIL_BLOCK_ROUTER_GRADIENT'),
            'per_block':per_block,
        }

    @staticmethod
    def _attach_router_gradient_health(routing_diag, gradient_health):
        if routing_diag is None:
            return None
        diag=dict(routing_diag); gh=dict(gradient_health or {})
        by_id={int(row.get('block_id',-1)):row for row in (gh.get('per_block') or [])}
        blocks=[]
        for row0 in (diag.get('blocks') or []):
            row=dict(row0); g=by_id.get(int(row.get('block_id',-1)),{})
            row['router_gradient_max']=float(g.get('router_gradient_max',0.0))
            row['router_gradient_mean']=float(g.get('router_gradient_mean',0.0))
            row['router_gradient_status']=str(g.get('router_gradient_status','FAIL_MISSING_ROUTER_GRADIENT_EVIDENCE'))
            routing_status=str(row.get('routing_distribution_status','PASS'))
            if row['router_gradient_status']!='PASS':
                row['routing_health_status']='FAIL_ROUTER_GRADIENT'
            else:
                row['routing_health_status']=routing_status
            blocks.append(row)
        diag['blocks']=blocks
        diag['router_gradient_health']=gh
        failed_grad=[int(r['block_id']) for r in blocks if r.get('router_gradient_status')!='PASS']
        failed_routing=[int(r['block_id']) for r in blocks if r.get('routing_distribution_status')!='PASS']
        diag['failed_router_gradient_block_ids']=failed_grad
        diag['nonpass_routing_block_ids']=failed_routing
        if failed_grad:
            overall='FAIL_ROUTER_GRADIENT'
        elif any(r.get('obvious_single_expert_collapse') for r in blocks):
            overall='WARN_OBVIOUS_SINGLE_EXPERT_COLLAPSE'
        elif failed_routing:
            overall='WARN_DEAD_EXPERTS_OBSERVED'
        else:
            overall='PASS'
        diag['routing_health_status']=overall
        diag['per_block_authority']=True
        diag['aggregate_summary_authoritative']=False
        return diag

    def _restored_checkpoint_router_gradient_probe(self, seq, y, sw, criterion):
        """Deterministically probe each router after best-checkpoint restoration.

        This performs backward passes only; parameters are never stepped.  The resulting
        per-block norms therefore describe the exact restored model used for routing
        diagnostics rather than a different/last training epoch.
        """
        if self.architecture!='transformer_moe' or self.model_ is None:
            return None
        seq=np.asarray(seq,dtype=np.float32); y=np.asarray(y,dtype=np.int64); sw=np.asarray(sw,dtype=np.float32)
        samples=[[] for _ in range(len(self.model_.blocks))]
        self.model_.eval(); bs=max(8,self.batch_size)
        for start in range(0,len(seq),bs):
            xb=torch.from_numpy(seq[start:start+bs]).to(self.device)
            yb=torch.from_numpy(y[start:start+bs]).to(self.device)
            wb=torch.from_numpy(sw[start:start+bs]).to(self.device)
            self.model_.zero_grad(set_to_none=True)
            probs=self.model_(xb).clamp_min(1e-8); lv=criterion(torch.log(probs),yb)
            loss=(lv*wb).sum()/wb.sum().clamp_min(1e-8)
            if self.load_balance_coef>0:
                loss=loss+self.load_balance_coef*self.model_.router_balance_loss()
            loss.backward()
            for block_id,norm in enumerate(self._router_grad_norms(self.model_)):
                samples[block_id].append(norm)
        self.model_.zero_grad(set_to_none=True); self.model_.eval()
        health=self._router_gradient_health_from_samples(samples)
        health['gradient_weight_source']='RESTORED_BEST_EARLYSTOP_CHECKPOINT_DETERMINISTIC_OBJECTIVE_PROBE'
        return health

    def _routing_diagnostics_from_sequences(self, seq, *, best_epoch:int, router_gradient_health=None):
        if self.architecture!='transformer_moe' or self.model_ is None:
            return None
        seq=np.asarray(seq,dtype=np.float32)
        if len(seq)==0: return None
        n_blocks=len(self.model_.blocks)
        block_dispatch=[np.zeros(self.num_experts,dtype=np.float64) for _ in range(n_blocks)]
        block_soft=[np.zeros(self.num_experts,dtype=np.float64) for _ in range(n_blocks)]
        block_entropy=[0.0 for _ in range(n_blocks)]; block_total=[0.0 for _ in range(n_blocks)]
        self.model_.eval(); bs=max(32,self.batch_size)
        with torch.no_grad():
            for start in range(0,len(seq),bs):
                xb=torch.from_numpy(seq[start:start+bs]).to(self.device); self.model_(xb)
                weight=float(len(xb)*xb.shape[1]); snaps=self.model_.routing_snapshots()
                if len(snaps)!=n_blocks:
                    raise RuntimeError(f'MoE routing snapshot block mismatch: expected {n_blocks}, got {len(snaps)}')
                for block_id,snap in enumerate(snaps):
                    block_dispatch[block_id] += snap['dispatch_share'].cpu().numpy().astype(np.float64)*weight
                    block_soft[block_id] += snap['mean_soft_probability'].cpu().numpy().astype(np.float64)*weight
                    block_entropy[block_id] += float(snap['routing_entropy'].cpu().item())*weight
                    block_total[block_id] += weight
        blocks=[]
        for block_id in range(n_blocks):
            total=block_total[block_id]
            if total<=0:
                raise RuntimeError(f'MoE block {block_id} has no routing diagnostic observations')
            dispatch=block_dispatch[block_id]/total; soft=block_soft[block_id]/total
            if dispatch.sum()>0: dispatch/=dispatch.sum()
            if soft.sum()>0: soft/=soft.sum()
            positive=dispatch[dispatch>0]
            dispatch_entropy=float(-np.sum(positive*np.log(positive))) if len(positive) else 0.0
            dead=int(np.sum(dispatch<=1e-12)); effective=float(math.exp(dispatch_entropy)) if len(positive) else 0.0
            max_share=float(dispatch.max()) if len(dispatch) else 0.0; min_share=float(dispatch.min()) if len(dispatch) else 0.0
            obvious=bool(max_share>=1.0-1e-12 and dead>=self.num_experts-1)
            distribution_status=('WARN_OBVIOUS_SINGLE_EXPERT_COLLAPSE' if obvious else ('WARN_DEAD_EXPERTS_OBSERVED' if dead>0 else 'PASS'))
            blocks.append({
                'block_id':int(block_id),'expert_dispatch_share':[float(x) for x in dispatch.tolist()],
                'mean_soft_router_probability':[float(x) for x in soft.tolist()],
                'routing_entropy':float(block_entropy[block_id]/total),'dispatch_entropy':dispatch_entropy,
                'maximum_expert_share':max_share,'minimum_expert_share':min_share,'dead_expert_count':dead,
                'effective_expert_count':effective,'effective_utilization':float(effective/max(1,self.num_experts)),
                'obvious_single_expert_collapse':obvious,'routing_distribution_status':distribution_status,
                'router_gradient_max':0.0,'router_gradient_mean':0.0,
                'router_gradient_status':'FAIL_MISSING_ROUTER_GRADIENT_EVIDENCE',
                'routing_health_status':distribution_status,
            })
        # Whole-model aggregate is retained only for backward-compatible visualization.
        agg_dispatch=np.mean(np.stack([np.asarray(r['expert_dispatch_share'],dtype=np.float64) for r in blocks]),axis=0)
        agg_soft=np.mean(np.stack([np.asarray(r['mean_soft_router_probability'],dtype=np.float64) for r in blocks]),axis=0)
        if agg_dispatch.sum()>0: agg_dispatch/=agg_dispatch.sum()
        if agg_soft.sum()>0: agg_soft/=agg_soft.sum()
        pos=agg_dispatch[agg_dispatch>0]
        agg_entropy=float(-np.sum(pos*np.log(pos))) if len(pos) else 0.0
        agg_dead=int(np.sum(agg_dispatch<=1e-12)); agg_effective=float(math.exp(agg_entropy)) if len(pos) else 0.0
        diag={
            'schema':'MAX_MOE_ROUTING_DIAGNOSTICS_V2','authority':'PER_MOE_BLOCK',
            'expert_identity':'LATENT_LEARNED_EXPERTS','num_experts':int(self.num_experts),'num_blocks':int(n_blocks),'top_k':int(self.top_k),
            'blocks':blocks,'per_block_authority':True,'aggregate_summary_authoritative':False,
            'expert_dispatch_share':[float(x) for x in agg_dispatch.tolist()],
            'mean_soft_router_probability':[float(x) for x in agg_soft.tolist()],
            'routing_entropy':float(np.mean([r['routing_entropy'] for r in blocks])),
            'dispatch_entropy':agg_entropy,'maximum_expert_share':float(agg_dispatch.max()) if len(agg_dispatch) else 0.0,
            'minimum_expert_share':float(agg_dispatch.min()) if len(agg_dispatch) else 0.0,
            'dead_expert_count':agg_dead,'effective_expert_count':agg_effective,
            'effective_utilization':float(agg_effective/max(1,self.num_experts)),
            'obvious_single_expert_collapse':bool(any(r['obvious_single_expert_collapse'] for r in blocks)),
            'routing_health_status':('WARN_OBVIOUS_SINGLE_EXPERT_COLLAPSE' if any(r['obvious_single_expert_collapse'] for r in blocks) else ('WARN_DEAD_EXPERTS_OBSERVED' if any(r['routing_distribution_status']!='PASS' for r in blocks) else 'PASS')) ,
            'best_checkpoint_epoch':int(best_epoch),'diagnostic_weight_source':'RESTORED_BEST_EARLYSTOP_CHECKPOINT',
        }
        return self._attach_router_gradient_health(diag, router_gradient_health) if router_gradient_health is not None else diag

    def _fit_prebuilt(self, seq, y, sample_weight=None, *, row_ids=None, purge_bars=0, label_horizon_bars=0):
        self._seed(); seq = np.asarray(seq, dtype=np.float32); y = np.asarray(y, dtype=np.int64)
        sw=np.ones(len(y),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        if len(sw)!=len(y): raise ValueError("Temporal sample_weight length mismatch")
        if seq.ndim != 3 or len(seq) != len(y):
            raise ValueError(f"Temporal fit expects matching [N,T,F]/[N], got {seq.shape}/{y.shape}")
        required = set(range(self.n_classes))
        if set(np.unique(y).tolist()) != required:
            raise ValueError(f"Temporal model requires classes {sorted(required)}, got {np.unique(y).tolist()}")
        n=len(seq)
        if row_ids is None:
            tr_idx=np.arange(n,dtype=int); va_idx=np.empty(0,dtype=int); use_earlystop=False
            internal={
                'schema':'MAX_DL_INTERNAL_EARLYSTOP_PURGE_V1','mode':'NO_EARLYSTOP_DIRECT_FIT',
                'effective_horizon_bars':None,'applied_purge_bars':None,
                'train_supervised_rows':int(n),'validation_supervised_rows':0,
                'validation_context_preserved':True,'overlap_check':'NOT_APPLICABLE',
            }
        else:
            rows=np.asarray(row_ids,dtype=int).reshape(-1)
            if len(rows)!=n: raise ValueError('Temporal internal row-id length mismatch')
            horizon=max(0,int(label_horizon_bars or 0)); horizon=horizon if horizon>0 else max(0,int(purge_bars or 0))
            if horizon<=0:
                tr_idx=np.arange(n,dtype=int); va_idx=np.empty(0,dtype=int); use_earlystop=False
                internal={'schema':'MAX_DL_INTERNAL_EARLYSTOP_PURGE_V1','mode':'NO_EARLYSTOP_NO_HORIZON_AUTHORITY','effective_horizon_bars':None,'applied_purge_bars':None,'train_supervised_rows':int(n),'validation_supervised_rows':0,'validation_context_preserved':True,'overlap_check':'NOT_APPLICABLE'}
            else:
                val_n=max(24,int(round(n*0.15))) if n>=180 else max(12,int(round(n*0.20)))
                val_n=min(max(1,val_n),max(1,n//3))
                split=purged_internal_earlystop_split(rows,validation_rows=val_n,purge_bars=int(purge_bars or 0),label_horizon_bars=horizon,min_train_rows=40,min_validation_rows=8)
                tr_idx,va_idx=split.train_positions,split.validation_positions; use_earlystop=True; internal=dict(split.evidence); internal['mode']='PURGED_EARLYSTOP'
        Xtr=seq[tr_idx]; ytr=y[tr_idx]; swtr=sw[tr_idx]
        Xva=seq[va_idx] if len(va_idx) else np.empty((0,)+seq.shape[1:],dtype=np.float32); yva=y[va_idx] if len(va_idx) else np.empty(0,dtype=np.int64); swva=sw[va_idx] if len(va_idx) else np.empty(0,dtype=np.float32)
        if set(np.unique(ytr).tolist()) != required:
            raise ValueError(f"Temporal purged internal train requires classes {sorted(required)}, got {np.unique(ytr).tolist()}")
        flat = Xtr.reshape(-1, Xtr.shape[-1]); self.feature_mean_ = flat.mean(0).astype(np.float32); self.feature_std_ = flat.std(0).astype(np.float32)
        self.feature_std_[self.feature_std_ < 1e-6] = 1.0
        self.model_ = self._make_model(seq.shape[-1])
        counts = np.bincount(ytr, minlength=self.n_classes).astype(np.float64)
        weights = counts.sum() / np.maximum(counts, 1.0); weights /= max(weights.mean(), 1e-12)
        criterion = nn.NLLLoss(weight=torch.as_tensor(weights, dtype=torch.float32, device=self.device), reduction="none")
        opt = torch.optim.AdamW(self.model_.parameters(), lr=self.learning_rate, weight_decay=self.weight_decay)
        Xt = torch.from_numpy(Xtr); yt = torch.from_numpy(ytr); Wt=torch.from_numpy(swtr)
        if use_earlystop:
            Xv=torch.from_numpy(Xva).to(self.device); yv=torch.from_numpy(yva).to(self.device); Wv=torch.from_numpy(swva).to(self.device)
        gen = torch.Generator().manual_seed(self.random_state); best_state = copy.deepcopy(self.model_.state_dict())
        best_loss = math.inf; best_epoch = 0; stale = 0; ran = 0; router_grad_norms_by_block=[[] for _ in range(len(self.model_.blocks))] if self.architecture=='transformer_moe' else []
        for epoch in range(1, self.epochs + 1):
            self.model_.train(); order = torch.randperm(len(Xt), generator=gen)
            for start in range(0, len(order), max(8, self.batch_size)):
                idx = order[start:start + max(8, self.batch_size)]
                xb = Xt[idx].to(self.device); yb = yt[idx].to(self.device); wb=Wt[idx].to(self.device)
                probs = self.model_(xb).clamp_min(1e-8); lv=criterion(torch.log(probs), yb); loss=(lv*wb).sum()/wb.sum().clamp_min(1e-8)
                if self.architecture == "transformer_moe" and self.load_balance_coef > 0:
                    loss = loss + self.load_balance_coef * self.model_.router_balance_loss()
                opt.zero_grad(set_to_none=True); loss.backward()
                if self.architecture=='transformer_moe':
                    for block_id,norm in enumerate(self._router_grad_norms(self.model_)):
                        router_grad_norms_by_block[block_id].append(norm)
                torch.nn.utils.clip_grad_norm_(self.model_.parameters(), 2.0); opt.step()
            ran = epoch
            if use_earlystop:
                self.model_.eval()
                with torch.no_grad():
                    vl=criterion(torch.log(self.model_(Xv).clamp_min(1e-8)), yv); vloss=float(((vl*Wv).sum()/Wv.sum().clamp_min(1e-8)).item())
                if vloss < best_loss - 1e-5:
                    best_loss = vloss; best_epoch = epoch; best_state = copy.deepcopy(self.model_.state_dict()); stale = 0
                else: stale += 1
                if stale >= self.patience: break
            else:
                best_epoch=epoch; best_state=copy.deepcopy(self.model_.state_dict())
        self.model_.load_state_dict(best_state); self.model_.eval(); self.internal_validation_=internal
        if self.architecture=='transformer_moe':
            training_history_health=self._router_gradient_health_from_samples(router_grad_norms_by_block)
            diag_seq=Xva if use_earlystop and len(Xva) else Xtr
            diag_y=yva if use_earlystop and len(Xva) else ytr
            diag_sw=swva if use_earlystop and len(Xva) else swtr
            restored_router_signature=self._router_parameter_signature()
            self.router_gradient_health_=self._restored_checkpoint_router_gradient_probe(diag_seq,diag_y,diag_sw,criterion)
            if self.router_gradient_health_ is not None:
                self.router_gradient_health_['training_history']=training_history_health
                self.router_gradient_health_['checkpoint_router_signature']=restored_router_signature
            self.routing_diagnostics_=self._routing_diagnostics_from_sequences(
                diag_seq,best_epoch=best_epoch,router_gradient_health=self.router_gradient_health_)
            if self.routing_diagnostics_ is not None:
                self.routing_diagnostics_['checkpoint_router_signature']=restored_router_signature
                self.routing_diagnostics_['diagnostics_recomputed_after_restore']=True
                self.routing_diagnostics_['router_gradient_recomputed_after_restore']=True
        else:
            self.router_gradient_health_=None; self.routing_diagnostics_=None
        self.train_report_ = TemporalTrainReport(self.architecture, ran, best_epoch, None if not use_earlystop else float(best_loss), int(len(Xtr)), int(len(Xva)), dict(internal), None if self.routing_diagnostics_ is None else dict(self.routing_diagnostics_))
        return self

    def fit(self, X, y, sample_weight=None):
        X=np.asarray(X,dtype=np.float32); y=np.asarray(y,dtype=np.int64)
        seq=sequence_tensor(X,self.sequence_length)
        sw=np.ones(len(y),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        keep=sw>0
        return self._fit_prebuilt(seq[keep],y[keep],sw[keep])

    def fit_indexed(self, X, y, indices, purge_bars=0, embargo_bars=0, label_horizon_bars=None, sample_weight=None):
        X=np.asarray(X,dtype=np.float32); y=np.asarray(y,dtype=np.int64)
        seq,rows=sequence_tensor_for_indices(X,indices,self.sequence_length)
        if len(rows)==0: raise ValueError("Temporal fit_indexed received no legal rows")
        sw=np.ones(len(y),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        keep=sw[rows]>0
        if not np.any(keep): raise ValueError("Temporal fit_indexed has no supervised target rows")
        horizon=int(purge_bars if label_horizon_bars is None else label_horizon_bars)
        return self._fit_prebuilt(seq[keep],y[rows][keep],sw[rows][keep],row_ids=rows[keep],purge_bars=purge_bars,label_horizon_bars=horizon)

    def _predict_sequences(self, seq):
        if self.model_ is None: raise RuntimeError("TemporalClassifier is not fitted")
        seq = np.asarray(seq, dtype=np.float32); out = []; bs = max(64, self.batch_size * 2); self.model_.eval()
        with torch.no_grad():
            for start in range(0, len(seq), bs):
                out.append(self.model_(torch.from_numpy(seq[start:start + bs]).to(self.device)).cpu().numpy())
        return np.vstack(out).astype(np.float64) if out else np.empty((0, self.n_classes), dtype=np.float64)

    def predict_proba(self, X):
        return self._predict_sequences(sequence_tensor(np.asarray(X, dtype=np.float32), self.sequence_length))

    def predict_proba_with_context(self, history_X, target_X):
        return self._predict_sequences(sequence_tensor_with_context(history_X, target_X, self.sequence_length))

    def predict_proba_indexed(self, X, target_indices, allowed_indices):
        X = np.asarray(X, dtype=np.float32); allowed = sorted_unique_indices(allowed_indices); targets = sorted_unique_indices(target_indices)
        if len(targets) == 0: return np.empty((0, self.n_classes), dtype=np.float64)
        seq, rows = sequence_tensor_for_indices(X, allowed, self.sequence_length); pos = {int(r): i for i, r in enumerate(rows)}
        try: take = np.asarray([pos[int(r)] for r in targets], dtype=int)
        except KeyError as exc: raise ValueError(f"Target row {exc.args[0]} is outside allowed temporal context") from exc
        return self._predict_sequences(seq[take])

    def onnx_input(self, X): return sequence_tensor(np.asarray(X, dtype=np.float32), self.sequence_length)
    def onnx_input_with_context(self, history_X, target_X): return sequence_tensor_with_context(history_X, target_X, self.sequence_length)
    def export_module(self):
        if self.model_ is None: raise RuntimeError("TemporalClassifier is not fitted")
        return self.model_
    @property
    def input_shape_(self):
        return [1, int(self.sequence_length), int(len(self.feature_mean_))] if self.feature_mean_ is not None else [1, int(self.sequence_length), 32]

    @property
    def parameter_count_(self):
        return int(sum(p.numel() for p in self.model_.parameters())) if self.model_ is not None else None

    def expert_usage(self):
        if self.model_ is None or not hasattr(self.model_,"expert_usage"):
            return None
        u=self.model_.expert_usage()
        return None if u is None else [float(x) for x in u.detach().cpu().numpy().tolist()]

    def routing_diagnostics(self):
        return None if self.routing_diagnostics_ is None else dict(self.routing_diagnostics_)


class TemporalDirectionClassifier(TemporalClassifier):
    """DOWN/UP-only temporal encoder. SKIP rows remain causal context but are not targets."""
    def __init__(self, **kwargs):
        kwargs["n_classes"] = 2
        super().__init__(**kwargs)
        self.classes_ = np.asarray([0, 1], dtype=np.int64)

    @staticmethod
    def _direction_targets(y3):
        y3 = np.asarray(y3, dtype=np.int64); mask = y3 != 1; y2 = (y3[mask] == 2).astype(np.int64)
        return mask, y2

    def _fit_direction(self, seq_all, y3, sample_weight=None, *, row_ids=None, purge_bars=0, label_horizon_bars=0):
        seq_all=np.asarray(seq_all,dtype=np.float32); y3=np.asarray(y3,dtype=np.int64)
        sw=np.ones(len(y3),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        mask=(y3!=1)&(sw>0); idx=np.flatnonzero(mask); y2=(y3[idx]==2).astype(np.int64)
        if len(idx)<40 or set(np.unique(y2).tolist())!={0,1}:
            raise ValueError("Temporal direction model requires >=40 supervised directional rows and both SELL/BUY classes")
        rows=None if row_ids is None else np.asarray(row_ids,dtype=int)[idx]
        return super()._fit_prebuilt(seq_all[idx],y2,sw[idx],row_ids=rows,purge_bars=purge_bars,label_horizon_bars=label_horizon_bars)

    def fit(self, X, y3, sample_weight=None):
        X=np.asarray(X,dtype=np.float32)
        return self._fit_direction(sequence_tensor(X,self.sequence_length),y3,sample_weight)

    def fit_indexed(self, X, y3, indices, purge_bars=0, embargo_bars=0, label_horizon_bars=None, sample_weight=None):
        X=np.asarray(X,dtype=np.float32); y3=np.asarray(y3,dtype=np.int64)
        seq,rows=sequence_tensor_for_indices(X,indices,self.sequence_length)
        if len(rows)==0: raise ValueError("Temporal direction fit_indexed received no legal rows")
        sw=np.ones(len(y3),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        horizon=int(purge_bars if label_horizon_bars is None else label_horizon_bars)
        return self._fit_direction(seq,y3[rows],sw[rows],row_ids=rows,purge_bars=purge_bars,label_horizon_bars=horizon)

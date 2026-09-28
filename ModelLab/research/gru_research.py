from __future__ import annotations

import copy
import math
from dataclasses import dataclass

import numpy as np

from core.temporal_index import contiguous_chunks, sorted_unique_indices, purged_internal_earlystop_split

try:
    import torch
    import torch.nn as nn
except Exception as exc:  # explicit dependency failure when GRU is actually imported
    raise RuntimeError("GRU requires PyTorch. Re-run START_UI.cmd to install the v0.7.1 dependency stack.") from exc


def sequence_tensor(X, sequence_length: int) -> np.ndarray:
    """Causal [N,T,F] windows ending at each row, left-padded with oldest available row."""
    X = np.asarray(X, dtype=np.float32)
    if X.ndim != 2:
        raise ValueError(f"GRU expects [N,F] source matrix, got {X.shape}")
    n, f = X.shape
    if n == 0:
        return np.empty((0, max(2, int(sequence_length)), f), dtype=np.float32)
    t = max(2, int(sequence_length))
    out = np.empty((n, t, f), dtype=np.float32)
    for i in range(n):
        start = max(0, i - t + 1)
        block = X[start : i + 1]
        pad = t - len(block)
        if pad:
            out[i, :pad] = block[0]
            out[i, pad:] = block
        else:
            out[i] = block
    return out


def sequence_tensor_with_context(history_X, target_X, sequence_length: int) -> np.ndarray:
    """Causal target sequences using only rows available before/at each target.

    history_X is strictly earlier than target_X. This mirrors live MT5 rolling-buffer
    inference and prevents validation-fold warmup from being fabricated from the first
    validation row.
    """
    history=np.asarray(history_X,dtype=np.float32)
    target=np.asarray(target_X,dtype=np.float32)
    if target.ndim!=2:
        raise ValueError(f"target_X must be [N,F], got {target.shape}")
    if history.size==0:
        history=np.empty((0,target.shape[1]),dtype=np.float32)
    if history.ndim!=2 or history.shape[1]!=target.shape[1]:
        raise ValueError(f"history/target feature mismatch: {history.shape} vs {target.shape}")
    t=max(2,int(sequence_length))
    if len(target)==0:
        return np.empty((0,t,target.shape[1]),dtype=np.float32)
    keep=max(0,t-1)
    prefix=history[-keep:] if keep else history[:0]
    combined=np.vstack([prefix,target])
    all_seq=sequence_tensor(combined,t)
    return all_seq[len(prefix):]


def sequence_tensor_for_indices(X, indices, sequence_length: int) -> tuple[np.ndarray, np.ndarray]:
    """Build causal sequences for original row ids without crossing excluded gaps.

    Returned row ids are sorted and align one-to-one with the sequence tensor. A gap in
    ``indices`` resets temporal context, so CPCV-held-out blocks can never become fake
    adjacency in GRU training.
    """
    X=np.asarray(X,dtype=np.float32)
    if X.ndim!=2:
        raise ValueError(f"GRU expects [N,F] source matrix, got {X.shape}")
    idx=sorted_unique_indices(indices)
    t=max(2,int(sequence_length))
    if len(idx)==0:
        return np.empty((0,t,X.shape[1]),dtype=np.float32), idx
    seq_parts=[]; row_parts=[]
    for chunk in contiguous_chunks(idx):
        block=X[chunk]
        seq_parts.append(sequence_tensor(block,t))
        row_parts.append(chunk)
    return np.concatenate(seq_parts,axis=0), np.concatenate(row_parts)


class GRUNet(nn.Module):
    def __init__(self, n_features: int, hidden_size: int, num_layers: int, dropout: float, mean, std):
        super().__init__()
        self.register_buffer("feature_mean", torch.as_tensor(mean, dtype=torch.float32).view(1, 1, -1))
        self.register_buffer("feature_std", torch.as_tensor(std, dtype=torch.float32).view(1, 1, -1))
        self.gru = nn.GRU(
            input_size=int(n_features), hidden_size=int(hidden_size), num_layers=int(num_layers),
            dropout=float(dropout) if int(num_layers) > 1 else 0.0, batch_first=True,
        )
        self.head = nn.Linear(int(hidden_size), 3)

    def forward(self, x):
        x = (x - self.feature_mean) / self.feature_std
        y, _ = self.gru(x)
        return torch.softmax(self.head(y[:, -1, :]), dim=1)


@dataclass
class GRUTrainReport:
    epochs_ran: int
    best_epoch: int
    best_val_loss: float | None
    train_rows: int
    val_rows: int
    internal_validation: dict | None = None


class GRUClassifier:
    """Small CPU GRU with sklearn-like fit/predict_proba and sequence ONNX export support."""

    def __init__(self, *, sequence_length=12, hidden_size=32, num_layers=1, dropout=0.0,
                 learning_rate=0.001, batch_size=128, epochs=16, weight_decay=0.0001,
                 patience=4, random_state=42, threads=4, device="cpu", compute_backend="CPU"):
        self.sequence_length=int(sequence_length); self.hidden_size=int(hidden_size); self.num_layers=int(num_layers)
        self.dropout=float(dropout); self.learning_rate=float(learning_rate); self.batch_size=int(batch_size)
        self.epochs=int(epochs); self.weight_decay=float(weight_decay); self.patience=int(patience)
        self.random_state=int(random_state); self.threads=int(threads)
        self.device_name=str(device or "cpu"); self.compute_backend=str(compute_backend or "CPU")
        self.device=torch.device(self.device_name)
        self.classes_=np.asarray([0,1,2],dtype=np.int64)
        self.model_=None; self.feature_mean_=None; self.feature_std_=None; self.train_report_=None; self.internal_validation_=None

    def _seed(self):
        torch.manual_seed(self.random_state); np.random.seed(self.random_state)
        try: torch.set_num_threads(max(1,self.threads))
        except Exception: pass

    def _fit_prebuilt(self, seq, y, sample_weight=None, *, row_ids=None, purge_bars=0, label_horizon_bars=0):
        self._seed(); seq=np.asarray(seq,dtype=np.float32); y=np.asarray(y,dtype=np.int64)
        sw=np.ones(len(y),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        if len(sw)!=len(y): raise ValueError("GRU sample_weight length mismatch")
        if seq.ndim!=3 or len(seq)!=len(y):
            raise ValueError(f"GRU fit expects matching [N,T,F]/[N], got {seq.shape}/{y.shape}")
        if set(np.unique(y).tolist())!={0,1,2}:
            raise ValueError(f"GRU requires classes [0,1,2], got {np.unique(y).tolist()}")
        n=len(seq)
        if row_ids is None:
            # Direct estimator.fit has no Strategy-geometry authority.  It therefore uses
            # fixed-epoch training with NO checkpoint-selection validation rather than an
            # unpurged early-stop split. Production research routes through fit_indexed.
            tr_idx=np.arange(n,dtype=int); va_idx=np.empty(0,dtype=int); use_earlystop=False
            internal={
                'schema':'MAX_DL_INTERNAL_EARLYSTOP_PURGE_V1','mode':'NO_EARLYSTOP_DIRECT_FIT',
                'effective_horizon_bars':None,'applied_purge_bars':None,
                'train_supervised_rows':int(n),'validation_supervised_rows':0,
                'validation_context_preserved':True,'overlap_check':'NOT_APPLICABLE',
            }
        else:
            rows=np.asarray(row_ids,dtype=int).reshape(-1)
            if len(rows)!=n: raise ValueError('GRU internal row-id length mismatch')
            horizon=max(0,int(label_horizon_bars or 0))
            # Compatibility for explicit callers that predate label_horizon_bars.
            # Production fit_model_indexed passes the exact Strategy horizon explicitly.
            if horizon<=0: horizon=max(0,int(purge_bars or 0))
            if horizon<=0:
                tr_idx=np.arange(n,dtype=int); va_idx=np.empty(0,dtype=int); use_earlystop=False
                internal={'schema':'MAX_DL_INTERNAL_EARLYSTOP_PURGE_V1','mode':'NO_EARLYSTOP_NO_HORIZON_AUTHORITY','effective_horizon_bars':None,'applied_purge_bars':None,'train_supervised_rows':int(n),'validation_supervised_rows':0,'validation_context_preserved':True,'overlap_check':'NOT_APPLICABLE'}
            else:
                val_n=max(32,int(round(n*0.15))) if n>=240 else max(12,int(round(n*0.20)))
                val_n=min(max(1,val_n),max(1,n//3))
                split=purged_internal_earlystop_split(
                    rows,validation_rows=val_n,purge_bars=int(purge_bars or 0),
                    label_horizon_bars=horizon,min_train_rows=50,min_validation_rows=8,
                )
                tr_idx,va_idx=split.train_positions,split.validation_positions; use_earlystop=True; internal=dict(split.evidence)
                internal['mode']='PURGED_EARLYSTOP'
        Xtr=seq[tr_idx]; ytr=y[tr_idx]; swtr=sw[tr_idx]
        Xva=seq[va_idx] if len(va_idx) else np.empty((0,)+seq.shape[1:],dtype=np.float32)
        yva=y[va_idx] if len(va_idx) else np.empty(0,dtype=np.int64); swva=sw[va_idx] if len(va_idx) else np.empty(0,dtype=np.float32)
        if set(np.unique(ytr).tolist())!={0,1,2}:
            raise ValueError(f"GRU purged internal train requires classes [0,1,2], got {np.unique(ytr).tolist()}")
        flat=Xtr.reshape(-1,Xtr.shape[-1]); self.feature_mean_=flat.mean(0).astype(np.float32); self.feature_std_=flat.std(0).astype(np.float32)
        self.feature_std_[self.feature_std_<1e-6]=1.0
        self.model_=GRUNet(seq.shape[-1],self.hidden_size,self.num_layers,self.dropout,self.feature_mean_,self.feature_std_).to(self.device)
        counts=np.bincount(ytr,minlength=3).astype(np.float64); weights=counts.sum()/np.maximum(counts,1.0); weights/=max(weights.mean(),1e-12)
        criterion=nn.NLLLoss(weight=torch.as_tensor(weights,dtype=torch.float32,device=self.device),reduction="none")
        opt=torch.optim.AdamW(self.model_.parameters(),lr=self.learning_rate,weight_decay=self.weight_decay)
        Xt=torch.from_numpy(Xtr); yt=torch.from_numpy(ytr); Wt=torch.from_numpy(swtr)
        if use_earlystop:
            Xv=torch.from_numpy(Xva).to(self.device); yv=torch.from_numpy(yva).to(self.device); Wv=torch.from_numpy(swva).to(self.device)
        gen=torch.Generator().manual_seed(self.random_state); best_state=copy.deepcopy(self.model_.state_dict()); best_loss=math.inf; best_epoch=0; stale=0; ran=0
        for epoch in range(1,self.epochs+1):
            self.model_.train(); order=torch.randperm(len(Xt),generator=gen)
            for start in range(0,len(order),max(8,self.batch_size)):
                idx=order[start:start+max(8,self.batch_size)]
                xb=Xt[idx].to(self.device); yb=yt[idx].to(self.device); wb=Wt[idx].to(self.device)
                probs=self.model_(xb).clamp_min(1e-8); lv=criterion(torch.log(probs),yb); loss=(lv*wb).sum()/wb.sum().clamp_min(1e-8)
                opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(self.model_.parameters(),2.0); opt.step()
            ran=epoch
            if use_earlystop:
                self.model_.eval()
                with torch.no_grad():
                    vl=criterion(torch.log(self.model_(Xv).clamp_min(1e-8)),yv); vloss=float(((vl*Wv).sum()/Wv.sum().clamp_min(1e-8)).item())
                if vloss<best_loss-1e-5: best_loss=vloss; best_epoch=epoch; best_state=copy.deepcopy(self.model_.state_dict()); stale=0
                else: stale+=1
                if stale>=self.patience: break
            else:
                best_epoch=epoch; best_state=copy.deepcopy(self.model_.state_dict())
        self.model_.load_state_dict(best_state); self.model_.eval(); self.internal_validation_=internal
        self.train_report_=GRUTrainReport(ran,best_epoch,None if not use_earlystop else float(best_loss),int(len(Xtr)),int(len(Xva)),dict(internal))
        return self

    def fit(self, X, y, sample_weight=None):
        X=np.asarray(X,dtype=np.float32); y=np.asarray(y,dtype=np.int64)
        if X.ndim!=2 or len(X)!=len(y):
            raise ValueError(f"GRU fit expects matching [N,F]/[N], got {X.shape}/{y.shape}")
        seq=sequence_tensor(X,self.sequence_length)
        sw=np.ones(len(y),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        keep=sw>0
        return self._fit_prebuilt(seq[keep],y[keep],sw[keep])

    def fit_indexed(self, X, y, indices, purge_bars=0, embargo_bars=0, label_horizon_bars=None, sample_weight=None):
        X=np.asarray(X,dtype=np.float32); y=np.asarray(y,dtype=np.int64)
        seq,rows=sequence_tensor_for_indices(X,indices,self.sequence_length)
        if len(rows)==0: raise ValueError("GRU fit_indexed received no legal training rows")
        sw=np.ones(len(y),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        keep=sw[rows]>0
        if not np.any(keep): raise ValueError("GRU fit_indexed has no supervised target rows")
        horizon=int(purge_bars if label_horizon_bars is None else label_horizon_bars)
        return self._fit_prebuilt(seq[keep],y[rows][keep],sw[rows][keep],row_ids=rows[keep],purge_bars=purge_bars,label_horizon_bars=horizon)

    def _predict_sequences(self, seq):
        if self.model_ is None: raise RuntimeError("GRUClassifier is not fitted")
        seq=np.asarray(seq,dtype=np.float32); out=[]; bs=max(64,self.batch_size*2); self.model_.eval()
        with torch.no_grad():
            for start in range(0,len(seq),bs): out.append(self.model_(torch.from_numpy(seq[start:start+bs]).to(self.device)).cpu().numpy())
        return np.vstack(out).astype(np.float64) if out else np.empty((0,3),dtype=np.float64)

    def predict_proba(self, X):
        return self._predict_sequences(sequence_tensor(np.asarray(X,dtype=np.float32),self.sequence_length))

    def predict_proba_with_context(self, history_X, target_X):
        return self._predict_sequences(sequence_tensor_with_context(history_X,target_X,self.sequence_length))

    def onnx_input(self, X): return sequence_tensor(np.asarray(X,dtype=np.float32),self.sequence_length)
    def onnx_input_with_context(self, history_X, target_X): return sequence_tensor_with_context(history_X,target_X,self.sequence_length)
    def export_module(self):
        if self.model_ is None: raise RuntimeError("GRUClassifier is not fitted")
        return self.model_
    @property
    def input_shape_(self): return [1,int(self.sequence_length),int(len(self.feature_mean_))] if self.feature_mean_ is not None else [1,int(self.sequence_length),32]


def note():
    return "GRU research is active with causal CP32 sequences; EA v1.06 provides matching rolling-buffer ONNX inference."

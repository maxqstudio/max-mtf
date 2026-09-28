from __future__ import annotations

import copy
import math
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.utils.class_weight import compute_sample_weight

try:
    import torch
    import torch.nn as nn
except Exception as exc:
    raise RuntimeError("Hybrid GRU research requires PyTorch. Re-run START_UI.cmd to install dependencies.") from exc

from research.gru_research import sequence_tensor, sequence_tensor_with_context, sequence_tensor_for_indices
from research.temporal_research import TemporalDirectionClassifier
from models.model_registry import hybrid_parts as registry_hybrid_parts
from core.temporal_index import inner_oof_folds, sorted_unique_indices, contiguous_chunks, purged_internal_earlystop_split


HYBRID_META_FEATURES = 4
HYBRID_INPUT_FEATURES = 32 + HYBRID_META_FEATURES


class DirectionGRUNet(nn.Module):
    """Binary DOWN/UP temporal encoder. It has no TAKE/SKIP or risk authority."""

    def __init__(self, n_features: int, hidden_size: int, num_layers: int, dropout: float, mean, std):
        super().__init__()
        self.register_buffer("feature_mean", torch.as_tensor(mean, dtype=torch.float32).view(1, 1, -1))
        self.register_buffer("feature_std", torch.as_tensor(std, dtype=torch.float32).view(1, 1, -1))
        self.gru = nn.GRU(
            input_size=int(n_features),
            hidden_size=int(hidden_size),
            num_layers=int(num_layers),
            dropout=float(dropout) if int(num_layers) > 1 else 0.0,
            batch_first=True,
        )
        self.head = nn.Linear(int(hidden_size), 2)

    def forward(self, x):
        x = (x - self.feature_mean) / self.feature_std
        y, _ = self.gru(x)
        return torch.softmax(self.head(y[:, -1, :]), dim=1)


@dataclass
class DirectionTrainReport:
    epochs_ran: int
    best_epoch: int
    best_val_loss: float | None
    directional_rows: int
    sell_rows: int
    buy_rows: int
    internal_validation: dict | None = None


class TemporalDirectionGRU:
    """GRU whose authority is direction only: class 0=DOWN/SELL, class 1=UP/BUY.

    It consumes the original 3-class training labels but ignores SKIP rows as targets.
    SKIP rows remain in the causal feature timeline, so temporal context is not distorted.
    """

    def __init__(
        self,
        *,
        sequence_length=12,
        hidden_size=24,
        num_layers=1,
        dropout=0.0,
        learning_rate=0.0015,
        batch_size=128,
        epochs=10,
        weight_decay=0.0001,
        patience=3,
        random_state=42,
        threads=4,
        device="cpu",
        compute_backend="CPU",
    ):
        self.sequence_length = int(sequence_length)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.learning_rate = float(learning_rate)
        self.batch_size = int(batch_size)
        self.epochs = int(epochs)
        self.weight_decay = float(weight_decay)
        self.patience = int(patience)
        self.random_state = int(random_state)
        self.threads = int(threads)
        self.device_name = str(device or "cpu")
        self.compute_backend = str(compute_backend or "CPU")
        self.device = torch.device(self.device_name)
        self.classes_ = np.asarray([0, 1], dtype=np.int64)
        self.model_ = None
        self.feature_mean_ = None
        self.feature_std_ = None
        self.train_report_ = None
        self.internal_validation_ = None

    def _seed(self):
        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)
        try:
            torch.set_num_threads(max(1, self.threads))
        except Exception:
            pass

    @staticmethod
    def _direction_targets(y3):
        y3 = np.asarray(y3, dtype=np.int64)
        mask = y3 != 1
        y2 = (y3[mask] == 2).astype(np.int64)
        return mask, y2

    def _fit_prebuilt(self, seq_all, y3, sample_weight=None, *, row_ids=None, purge_bars=0, label_horizon_bars=0):
        self._seed()
        seq_all=np.asarray(seq_all,dtype=np.float32); y3=np.asarray(y3,dtype=np.int64)
        sw=np.ones(len(y3),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        if len(sw)!=len(y3): raise ValueError("Direction GRU sample_weight length mismatch")
        if seq_all.ndim!=3 or len(seq_all)!=len(y3):
            raise ValueError(f"Direction GRU expects matching [N,T,F]/[N], got {seq_all.shape}/{y3.shape}")
        mask, _ = self._direction_targets(y3)
        idx = np.flatnonzero(mask & (sw>0))
        y_dir_all = np.full(len(y3), -1, dtype=np.int64); y_dir_all[idx] = (y3[idx] == 2).astype(np.int64)
        if len(idx) < 40 or set(np.unique(y_dir_all[idx]).tolist()) != {0, 1}:
            raise ValueError("Direction GRU requires >=40 directional rows and both SELL/BUY classes")
        if row_ids is None:
            tr_idx=idx; va_idx=np.empty(0,dtype=int); use_earlystop=False
            internal={'schema':'MAX_DL_INTERNAL_EARLYSTOP_PURGE_V1','mode':'NO_EARLYSTOP_DIRECT_FIT','effective_horizon_bars':None,'applied_purge_bars':None,'train_supervised_rows':int(len(idx)),'validation_supervised_rows':0,'validation_context_preserved':True,'overlap_check':'NOT_APPLICABLE'}
        else:
            rows=np.asarray(row_ids,dtype=int).reshape(-1)
            if len(rows)!=len(y3): raise ValueError('Direction GRU internal row-id length mismatch')
            supervised_rows=rows[idx]; horizon=max(0,int(label_horizon_bars or 0)); horizon=horizon if horizon>0 else max(0,int(purge_bars or 0))
            if horizon<=0:
                tr_idx=idx; va_idx=np.empty(0,dtype=int); use_earlystop=False
                internal={'schema':'MAX_DL_INTERNAL_EARLYSTOP_PURGE_V1','mode':'NO_EARLYSTOP_NO_HORIZON_AUTHORITY','effective_horizon_bars':None,'applied_purge_bars':None,'train_supervised_rows':int(len(idx)),'validation_supervised_rows':0,'validation_context_preserved':True,'overlap_check':'NOT_APPLICABLE'}
            else:
                val_n=max(16,int(round(len(idx)*0.18))); val_n=min(val_n,max(8,len(idx)//3))
                split=purged_internal_earlystop_split(supervised_rows,validation_rows=val_n,purge_bars=int(purge_bars or 0),label_horizon_bars=horizon,min_train_rows=40,min_validation_rows=8)
                tr_idx=idx[split.train_positions]; va_idx=idx[split.validation_positions]; use_earlystop=True; internal=dict(split.evidence); internal['mode']='PURGED_EARLYSTOP'
        ytr,yva=y_dir_all[tr_idx],y_dir_all[va_idx]; swtr,swva=sw[tr_idx],sw[va_idx]
        if set(np.unique(ytr).tolist()) != {0, 1}:
            raise ValueError("Direction GRU purged chronological train segment lost one direction class")
        Xtr=seq_all[tr_idx]
        flat=Xtr.reshape(-1,Xtr.shape[-1]); self.feature_mean_=flat.mean(0).astype(np.float32); self.feature_std_=flat.std(0).astype(np.float32); self.feature_std_[self.feature_std_<1e-6]=1.0
        self.model_=DirectionGRUNet(seq_all.shape[-1],self.hidden_size,self.num_layers,self.dropout,self.feature_mean_,self.feature_std_).to(self.device)
        counts=np.bincount(ytr,minlength=2).astype(np.float64); weights=counts.sum()/np.maximum(counts,1.0); weights/=max(weights.mean(),1e-12)
        criterion=nn.NLLLoss(weight=torch.as_tensor(weights,dtype=torch.float32,device=self.device),reduction="none")
        opt=torch.optim.AdamW(self.model_.parameters(),lr=self.learning_rate,weight_decay=self.weight_decay)
        Xt=torch.from_numpy(seq_all[tr_idx]); yt=torch.from_numpy(ytr); Wt=torch.from_numpy(swtr)
        if use_earlystop:
            Xv=torch.from_numpy(seq_all[va_idx]).to(self.device); yv=torch.from_numpy(yva).to(self.device); Wv=torch.from_numpy(swva).to(self.device)
        gen=torch.Generator().manual_seed(self.random_state); best_state=copy.deepcopy(self.model_.state_dict()); best_loss=math.inf; best_epoch=0; stale=0; ran=0; bs=max(8,self.batch_size)
        for epoch in range(1,self.epochs+1):
            self.model_.train(); order=torch.randperm(len(Xt),generator=gen)
            for start in range(0,len(order),bs):
                bi=order[start:start+bs]; xb=Xt[bi].to(self.device); yb=yt[bi].to(self.device); wb=Wt[bi].to(self.device)
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
        self.train_report_=DirectionTrainReport(ran,best_epoch,None if not use_earlystop else float(best_loss),int(len(idx)),int(np.sum(y_dir_all[idx]==0)),int(np.sum(y_dir_all[idx]==1)),dict(internal))
        return self

    def fit(self, X, y3, sample_weight=None):
        X=np.asarray(X,dtype=np.float32); y3=np.asarray(y3,dtype=np.int64)
        if X.ndim!=2 or len(X)!=len(y3): raise ValueError(f"Direction GRU expects matching [N,F]/[N], got {X.shape}/{y3.shape}")
        return self._fit_prebuilt(sequence_tensor(X,self.sequence_length),y3,sample_weight)

    def fit_indexed(self, X, y3, indices, purge_bars=0, embargo_bars=0, label_horizon_bars=None, sample_weight=None):
        X=np.asarray(X,dtype=np.float32); y3=np.asarray(y3,dtype=np.int64)
        seq,rows=sequence_tensor_for_indices(X,indices,self.sequence_length)
        if len(rows)==0: raise ValueError("Direction GRU fit_indexed received no legal rows")
        sw=np.ones(len(y3),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        horizon=int(purge_bars if label_horizon_bars is None else label_horizon_bars)
        return self._fit_prebuilt(seq,y3[rows],sw[rows],row_ids=rows,purge_bars=purge_bars,label_horizon_bars=horizon)

    def _predict_sequences(self, seq):
        if self.model_ is None:
            raise RuntimeError("TemporalDirectionGRU is not fitted")
        seq = np.asarray(seq, dtype=np.float32)
        out = []
        bs = max(64, self.batch_size * 2)
        self.model_.eval()
        with torch.no_grad():
            for start in range(0, len(seq), bs):
                out.append(self.model_(torch.from_numpy(seq[start:start + bs]).to(self.device)).cpu().numpy())
        return np.vstack(out).astype(np.float64) if out else np.empty((0, 2), dtype=np.float64)

    def predict_proba(self, X):
        return self._predict_sequences(sequence_tensor(np.asarray(X, dtype=np.float32), self.sequence_length))

    def predict_proba_with_context(self, history_X, target_X):
        seq = sequence_tensor_with_context(history_X, target_X, self.sequence_length)
        return self._predict_sequences(seq)

    def predict_proba_indexed(self, X, target_indices, allowed_indices):
        """Predict target rows using only contiguous context inside allowed_indices."""
        X=np.asarray(X,dtype=np.float32)
        allowed=sorted_unique_indices(allowed_indices); targets=sorted_unique_indices(target_indices)
        if len(targets)==0:
            return np.empty((0,2),dtype=np.float64)
        seq,rows=sequence_tensor_for_indices(X,allowed,self.sequence_length)
        pos={int(r):i for i,r in enumerate(rows)}
        try:
            take=np.asarray([pos[int(r)] for r in targets],dtype=int)
        except KeyError as exc:
            raise ValueError(f"Target row {exc.args[0]} is outside allowed temporal context") from exc
        return self._predict_sequences(seq[take])

    def onnx_input(self, X):
        return sequence_tensor(np.asarray(X, dtype=np.float32), self.sequence_length)

    def onnx_input_with_context(self, history_X, target_X):
        return sequence_tensor_with_context(history_X, target_X, self.sequence_length)

    def export_module(self):
        if self.model_ is None:
            raise RuntimeError("TemporalDirectionGRU is not fitted")
        return self.model_



def direction_meta_features(p2: np.ndarray) -> np.ndarray:
    p2 = np.asarray(p2, dtype=np.float32)
    if p2.ndim != 2 or p2.shape[1] != 2:
        raise ValueError(f"Expected direction probability [N,2], got {p2.shape}")
    p_down = p2[:, 0]
    p_up = p2[:, 1]
    directional = p_up - p_down
    confidence = np.maximum(p_up, p_down)
    return np.column_stack([p_down, p_up, directional, confidence]).astype(np.float32)


def augment_policy_features(X: np.ndarray, p2: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    return np.column_stack([X, direction_meta_features(p2)]).astype(np.float32)


class HybridStackClassifier:
    """Leakage-safe temporal(direction) -> classical SELL/SKIP/BUY policy stack.

    R7 keeps the proven OOF stacking contract but makes the temporal encoder a
    registry-selected component (GRU/LSTM/TCN/Transformer/PatchTST/iTransformer/TFT/MoE). The classical policy
    still sees only OOF temporal direction features; deterministic EA risk remains
    outside model authority.
    """

    def __init__(self, policy_family: str, *, temporal_family="gru", random_state=42, threads=4, patience=3, inner_folds=2, compute_plan=None, **params):
        self.policy_family = str(policy_family)
        self.temporal_family = str(temporal_family or "gru").lower()
        self.random_state = int(random_state)
        self.threads = int(threads)
        self.patience = int(patience)
        self.inner_folds = max(2,min(3,int(inner_folds)))
        self.params = dict(params)
        self.compute_plan = dict(compute_plan or {})
        self.classes_ = np.asarray([0, 1, 2], dtype=np.int64)
        self.direction_model_ = None
        self.policy_model_ = None
        self.oof_coverage_ratio_ = 0.0
        self.oof_rows_ = 0
        self.meta_feature_count_ = HYBRID_INPUT_FEATURES
        self.stacking_schema_ = "OOF_DIRECTION_STACK_V1"
        self.direction_authority_ = "DOWN_UP_ONLY"
        self.risk_authority_ = "DETERMINISTIC_EA"

    @property
    def sequence_length(self):
        return int(self.params.get("temporal_sequence_length", self.params.get("gru_sequence_length", 12)))

    def _tparam(self, key, default):
        return self.params.get(f"temporal_{key}", self.params.get(f"gru_{key}", default))

    def _direction_model(self, seed_offset=0):
        common = dict(
            sequence_length=int(self._tparam("sequence_length", 12)),
            hidden_size=int(self._tparam("hidden_size", 24)),
            num_layers=int(self._tparam("num_layers", 1)),
            dropout=float(self._tparam("dropout", 0.0)),
            learning_rate=float(self._tparam("learning_rate", 0.0015)),
            batch_size=int(self._tparam("batch_size", 128)),
            epochs=int(self._tparam("epochs", 10)),
            weight_decay=float(self._tparam("weight_decay", 0.0001)),
            patience=self.patience,
            random_state=self.random_state + int(seed_offset),
            threads=self.threads,
            device=str((self.compute_plan.get("temporal_dl") or {}).get("torch_device","cpu")),
            compute_backend=str((self.compute_plan.get("temporal_dl") or {}).get("backend","CPU")),
        )
        if self.temporal_family == "gru" and not any(k.startswith("temporal_") for k in self.params):
            # Exact R6 legacy behavior for historical GRU hybrids.
            return TemporalDirectionGRU(**common)
        return TemporalDirectionClassifier(
            architecture=self.temporal_family,
            tcn_channels=int(self._tparam("tcn_channels", self._tparam("hidden_size", 64))),
            tcn_blocks=int(self._tparam("tcn_blocks", 3)),
            kernel_size=int(self._tparam("kernel_size", 3)),
            d_model=int(self._tparam("d_model", self._tparam("hidden_size", 64))),
            attention_heads=int(self._tparam("attention_heads", 4)),
            ffn_mult=int(self._tparam("ffn_mult", 2)),
            expert_ffn=int(self._tparam("expert_ffn", max(64,int(self._tparam("d_model",self._tparam("hidden_size",64)))*2))),
            num_experts=int(self._tparam("num_experts",4)),
            top_k=int(self._tparam("top_k",1)),
            router_temperature=float(self._tparam("router_temperature",1.0)),
            load_balance_coef=float(self._tparam("load_balance_coef",0.01)),
            patch_len=int(self._tparam("patch_len",16)), patch_stride=int(self._tparam("patch_stride",8)),
            tft_lstm_layers=int(self._tparam("tft_lstm_layers",1)),
            **common,
        )

    def _policy_model(self):
        p = self.params
        if self.policy_family == "xgboost":
            from xgboost import XGBClassifier
            return XGBClassifier(
                n_estimators=int(p.get("policy_n_estimators", 400)),
                max_depth=int(p.get("policy_max_depth", 4)),
                learning_rate=float(p.get("policy_learning_rate", 0.05)),
                min_child_weight=float(p.get("policy_min_child_weight", 5.0)),
                subsample=float(p.get("policy_subsample", 0.85)),
                colsample_bytree=float(p.get("policy_colsample_bytree", 0.85)),
                reg_alpha=float(p.get("policy_reg_alpha", 0.0)),
                reg_lambda=float(p.get("policy_reg_lambda", 1.0)),
                objective="multi:softprob", num_class=3, eval_metric="mlogloss", tree_method="hist",
                n_jobs=self.threads, random_state=self.random_state,
                **({"device":"cuda"} if (self.compute_plan.get("xgboost") or {}).get("backend")=="CUDA" else {}),
            )
        if self.policy_family == "lightgbm":
            from lightgbm import LGBMClassifier
            subsample=float(p.get("policy_subsample", 0.85))
            return LGBMClassifier(
                n_estimators=int(p.get("policy_n_estimators", 500)),
                learning_rate=float(p.get("policy_learning_rate", 0.04)),
                num_leaves=int(p.get("policy_num_leaves", 31)),
                max_depth=int(p.get("policy_max_depth", 6)),
                min_child_samples=int(p.get("policy_min_child_samples", 40)),
                subsample=subsample,
                subsample_freq=1 if subsample < 0.999999 else 0,
                colsample_bytree=float(p.get("policy_colsample_bytree", 0.85)),
                reg_alpha=float(p.get("policy_reg_alpha", 0.0)),
                reg_lambda=float(p.get("policy_reg_lambda", 1.0)),
                objective="multiclass", num_class=3, n_jobs=self.threads, random_state=self.random_state, verbosity=-1,
                **({"device_type":"gpu"} if (self.compute_plan.get("lightgbm") or {}).get("backend")=="OPENCL_GPU" else {}),
            )
        if self.policy_family == "random_forest":
            return RandomForestClassifier(
                n_estimators=int(p.get("policy_n_estimators", 350)),
                max_depth=int(p.get("policy_max_depth", 12)),
                min_samples_leaf=int(p.get("policy_min_samples_leaf", 8)),
                max_features=float(p.get("policy_max_features", 0.65)),
                n_jobs=self.threads, random_state=self.random_state, class_weight="balanced_subsample",
            )
        raise ValueError(f"Unsupported hybrid policy family: {self.policy_family}")

    @staticmethod
    def _inner_folds(n: int, folds: int = 3):
        # Compatibility view for tests/callers; production research uses original row ids
        # through inner_oof_folds in fit_indexed.
        return inner_oof_folds(np.arange(int(n),dtype=int),folds,0,min_train_rows=100,min_validation_rows=20)

    def fit(self, X, y3, sample_weight=None):
        X=np.asarray(X,dtype=np.float32); y3=np.asarray(y3,dtype=np.int64)
        return self.fit_indexed(X,y3,np.arange(len(X),dtype=int),purge_bars=0,embargo_bars=0,sample_weight=sample_weight)

    def fit_indexed(self, X, y3, indices, purge_bars=0, embargo_bars=0, label_horizon_bars=None, sample_weight=None):
        """Fit OOF GRU→classical stack while preserving original chronology.

        The classical policy only sees GRU meta-features produced out-of-fold. CPCV
        complements may be discontinuous; original row ids are therefore preserved
        throughout and no temporal sequence may bridge a held-out gap.
        """
        X=np.asarray(X,dtype=np.float32); y3=np.asarray(y3,dtype=np.int64)
        authorized=sorted_unique_indices(indices)
        sw=np.ones(len(y3),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32)
        if len(sw)!=len(y3): raise ValueError("Hybrid sample_weight length mismatch")
        supervised=authorized[sw[authorized]>0]
        horizon=int(purge_bars if label_horizon_bars is None else label_horizon_bars)
        if X.ndim!=2 or len(X)!=len(y3):
            raise ValueError(f"Hybrid fit expects matching [N,F]/[N], got {X.shape}/{y3.shape}")
        if len(authorized)<120:
            raise ValueError(f"Hybrid indexed fit has too few authorized rows: {len(authorized)}")
        if set(np.unique(y3[supervised]).tolist()) != {0,1,2}:
            raise ValueError(f"Hybrid final policy requires supervised classes [0,1,2], got {np.unique(y3[supervised]).tolist()}")

        oof=np.full((len(X),2),np.nan,dtype=np.float64)
        folds=inner_oof_folds(authorized,self.inner_folds,int(purge_bars),min_train_rows=100,min_validation_rows=20)
        if not folds:
            raise ValueError("Hybrid could not construct legal purged inner OOF folds")
        for j,(tr,va) in enumerate(folds,1):
            dm=self._direction_model(seed_offset=j*101)
            try:
                dm.fit_indexed(X,y3,tr,purge_bars=purge_bars,embargo_bars=embargo_bars,label_horizon_bars=horizon,sample_weight=sw)
                oof[va]=dm.predict_proba_indexed(X,va,authorized)
            except ValueError:
                # A tiny/one-direction early segment is not allowed to leak; leave it uncovered.
                continue
        covered_idx=np.flatnonzero(np.isfinite(oof).all(axis=1) & (sw>0))
        if len(covered_idx)<max(80,int(0.20*len(authorized))):
            raise ValueError(f"Hybrid OOF direction coverage too small: {len(covered_idx)}/{len(authorized)}")
        if set(np.unique(y3[covered_idx]).tolist()) != {0,1,2}:
            raise ValueError("Hybrid OOF policy rows do not contain all SELL/SKIP/BUY classes")

        meta_X=augment_policy_features(X[covered_idx],oof[covered_idx])
        self.policy_model_=self._policy_model()
        if self.policy_family in {"xgboost","lightgbm"}:
            class_sw=compute_sample_weight(class_weight="balanced",y=y3[covered_idx]); train_sw=class_sw*sw[covered_idx]
            self.policy_model_.fit(meta_X,y3[covered_idx],sample_weight=train_sw)
        else:
            self.policy_model_.fit(meta_X,y3[covered_idx],sample_weight=sw[covered_idx])
        if list(getattr(self.policy_model_,"classes_",[])) != [0,1,2]:
            raise RuntimeError(f"Hybrid policy class order invalid: {getattr(self.policy_model_,'classes_',None)}")

        self.direction_model_=self._direction_model(seed_offset=999)
        self.direction_model_.fit_indexed(X,y3,authorized,purge_bars=purge_bars,embargo_bars=embargo_bars,label_horizon_bars=horizon,sample_weight=sw)
        self.oof_rows_=int(len(covered_idx))
        self.oof_coverage_ratio_=float(len(covered_idx)/max(1,len(authorized)))
        self.stacking_schema_="OOF_DIRECTION_STACK_V2_PURGED_INDEXED"
        self.temporal_train_chunks_=int(len(contiguous_chunks(authorized)))
        self.inner_purge_bars_=int(purge_bars)
        self.internal_label_horizon_bars_=int(horizon)
        self.temporal_internal_validation_=None if self.direction_model_ is None else getattr(self.direction_model_,'internal_validation_',None)
        self.temporal_routing_diagnostics_=None if self.direction_model_ is None else getattr(self.direction_model_,'routing_diagnostics_',None)
        return self

    def predict_proba(self, X):
        if self.direction_model_ is None or self.policy_model_ is None:
            raise RuntimeError("HybridStackClassifier is not fitted")
        X = np.asarray(X, dtype=np.float32)
        p2 = self.direction_model_.predict_proba(X)
        return np.asarray(self.policy_model_.predict_proba(augment_policy_features(X, p2)), dtype=np.float64)

    def predict_proba_with_context(self, history_X, target_X):
        if self.direction_model_ is None or self.policy_model_ is None:
            raise RuntimeError("HybridStackClassifier is not fitted")
        target_X = np.asarray(target_X, dtype=np.float32)
        p2 = self.direction_model_.predict_proba_with_context(history_X, target_X)
        return np.asarray(self.policy_model_.predict_proba(augment_policy_features(target_X, p2)), dtype=np.float64)

    def direction_proba_with_context(self, history_X, target_X):
        return self.direction_model_.predict_proba_with_context(history_X, target_X)

    def direction_onnx_input_with_context(self, history_X, target_X):
        return self.direction_model_.onnx_input_with_context(history_X, target_X)

    def policy_onnx_input_with_context(self, history_X, target_X):
        target_X = np.asarray(target_X, dtype=np.float32)
        p2 = self.direction_proba_with_context(history_X, target_X)
        return augment_policy_features(target_X, p2)


def hybrid_components(family: str) -> tuple[str,str]:
    parts=registry_hybrid_parts(family)
    if not parts:
        raise ValueError(family)
    return parts

def hybrid_policy_family(family: str) -> str:
    return hybrid_components(family)[1]

def hybrid_temporal_family(family: str) -> str:
    return hybrid_components(family)[0]

def is_hybrid_family(family: str) -> bool:
    return registry_hybrid_parts(family) is not None

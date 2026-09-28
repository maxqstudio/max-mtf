from __future__ import annotations

import copy
import importlib.metadata as md
import platform
import tempfile
import warnings
from pathlib import Path

import numpy as np
from models.model_registry import family_spec, is_hybrid_family, hybrid_parts
from core.artifact_paths import filesystem_safe_id

# Conservative standard-domain opset shared by every deployable tree converter.
# onnxmltools 1.16.0 (XGBoost/LightGBM) advertises converter support through opset 15.
# Using 17 here makes conversion fail before a model is even produced. Opset 15 is
# sufficient for the tree-classifier graphs and is also the safer MT5 portability target.
TARGET_OPSET = 15
EXPECTED_CLASSES = np.array([0, 1, 2], dtype=np.int64)

def _onnx_api():
    import onnx
    from onnx import TensorProto
    return onnx, TensorProto


def _pkg_version(name: str) -> str:
    try:
        return md.version(name)
    except Exception:
        return "unknown"


def converter_stack_versions() -> dict:
    return {
        "python": platform.python_version(),
        "numpy": _pkg_version("numpy"),
        "scikit-learn": _pkg_version("scikit-learn"),
        "xgboost": _pkg_version("xgboost"),
        "lightgbm": _pkg_version("lightgbm"),
        "onnx": _pkg_version("onnx"),
        "onnxruntime": _pkg_version("onnxruntime"),
        "skl2onnx": _pkg_version("skl2onnx"),
        "onnxmltools": _pkg_version("onnxmltools"),
        "torch": _pkg_version("torch"),
        "target_opset": TARGET_OPSET,
    }


def _probability_only(model_proto):
    onnx, TensorProto = _onnx_api()
    """Keep exactly one float tensor graph output, preferring [N,3] probabilities."""
    candidates = []
    for out in model_proto.graph.output:
        tt = out.type.tensor_type
        if tt.elem_type not in (TensorProto.FLOAT, TensorProto.DOUBLE):
            continue
        dims = tt.shape.dim
        score = 0
        name = out.name.lower()
        if "prob" in name:
            score += 20
        if len(dims) == 2:
            score += 5
        if len(dims) >= 2 and dims[1].HasField("dim_value") and dims[1].dim_value == 3:
            score += 50
        candidates.append((score, out))

    if not candidates:
        raise RuntimeError(
            "ONNX converter tidak mengekspos probability sebagai tensor. "
            "Untuk LightGBM converter harus zipmap=False."
        )

    _, selected = max(candidates, key=lambda x: x[0])
    if selected.type.tensor_type.elem_type != TensorProto.FLOAT:
        raise RuntimeError(
            "Probability output bukan float32; EA menggunakan vectorf + ONNX_NO_CONVERSION."
        )

    chosen = copy.deepcopy(selected)
    del model_proto.graph.output[:]
    model_proto.graph.output.extend([chosen])
    return model_proto


def _initial_types_for_family(family: str, n_features: int):
    """Use the tensor class owned by the converter that consumes it."""
    if family == "random_forest":
        from skl2onnx.common.data_types import FloatTensorType as SklearnFloatTensorType
        return [("input", SklearnFloatTensorType([None, n_features]))]
    if family in {"xgboost", "lightgbm"}:
        from onnxmltools.convert.common.data_types import FloatTensorType as OnnxMlToolsFloatTensorType
        return [("input", OnnxMlToolsFloatTensorType([None, n_features]))]
    if (family_spec(family) or {}).get("role") == "temporal":
        return None
    raise ValueError(f"Unsupported deployable family: {family}")


def _validate_model_class_order(model) -> None:
    classes = np.asarray(getattr(model, "classes_", []))
    if classes.shape != (3,) or not np.array_equal(classes.astype(np.int64), EXPECTED_CLASSES):
        raise RuntimeError(
            f"Classifier class order harus [0,1,2]=[SELL,SKIP,BUY], got {classes.tolist()}"
        )


def inspect_onnx_contract(proto, n_features: int = 32, sequence_length: int | None = None) -> dict:
    onnx, TensorProto = _onnx_api()
    if len(proto.graph.input) != 1:
        raise RuntimeError(f"Expected exactly one ONNX input, got {len(proto.graph.input)}")
    if len(proto.graph.output) != 1:
        raise RuntimeError(f"Expected exactly one ONNX output, got {len(proto.graph.output)}")

    inp = proto.graph.input[0]; out = proto.graph.output[0]
    it = inp.type.tensor_type; ot = out.type.tensor_type
    if it.elem_type != TensorProto.FLOAT: raise RuntimeError("ONNX input must be float32")
    if ot.elem_type != TensorProto.FLOAT: raise RuntimeError("ONNX output must be float32")
    idims = it.shape.dim; odims = ot.shape.dim
    expected_rank = 3 if sequence_length else 2
    if len(idims) != expected_rank:
        raise RuntimeError(f"ONNX input rank must be {expected_rank}, got {len(idims)}")
    if sequence_length:
        if not idims[0].HasField("dim_value") or int(idims[0].dim_value) != 1:
            raise RuntimeError("Temporal ONNX input batch dimension must be fixed to 1")
    feature_dim = 2 if sequence_length else 1
    if idims[feature_dim].HasField("dim_value") and idims[feature_dim].dim_value != n_features:
        raise RuntimeError(f"ONNX feature dimension mismatch: {idims[feature_dim].dim_value} != {n_features}")
    if sequence_length and idims[1].HasField("dim_value") and idims[1].dim_value != int(sequence_length):
        raise RuntimeError(f"ONNX sequence dimension mismatch: {idims[1].dim_value} != {sequence_length}")
    if len(odims) != 2: raise RuntimeError(f"ONNX output rank must be 2, got {len(odims)}")
    if odims[1].HasField("dim_value") and odims[1].dim_value != 3:
        raise RuntimeError(f"ONNX class dimension mismatch: {odims[1].dim_value} != 3")
    return {
        "input_name":inp.name,"output_name":out.name,"input_rank":len(idims),"output_rank":len(odims),
        "feature_count":n_features,"sequence_length":int(sequence_length) if sequence_length else 1,
        "runtime_batch_size":1 if sequence_length else None,
        "batch_contract":"FIXED_1" if sequence_length else "TABULAR_DYNAMIC",
        "class_count":3,"input_dtype":"float32","output_dtype":"float32",
    }


def _torch_export_fixed_batch_one(module, dummy, tmp: Path, output_name: str):
    """Export recurrent temporal ONNX under MAX's fixed batch=1 MT5 contract."""
    import torch
    if int(dummy.shape[0]) != 1:
        raise RuntimeError("Temporal ONNX export dummy batch must equal 1")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r".*Exporting a model to ONNX with a batch_size other than 1.*GRU.*")
        warnings.filterwarnings("ignore", message=r".*Exporting a model to ONNX with a batch_size other than 1.*LSTM.*")
        torch.onnx.export(
            module, dummy, str(tmp), input_names=["input"], output_names=[output_name],
            opset_version=TARGET_OPSET, do_constant_folding=True, dynamo=False,
        )


def _export_temporal(model, path: str | Path, n_features: int = 32):
    onnx, _ = _onnx_api()
    import torch
    _validate_model_class_order(model)
    seq_len = int(model.sequence_length)
    module = copy.deepcopy(model.export_module()).cpu().eval()
    dummy = torch.zeros((1, seq_len, n_features), dtype=torch.float32)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    _torch_export_fixed_batch_one(module,dummy,tmp,"probabilities")
    proto=onnx.load(tmp); onnx.checker.check_model(proto); inspect_onnx_contract(proto,n_features,seq_len)
    tmp.replace(path); return path

def export_tabular(model, family: str, path: str | Path, n_features: int = 32):
    onnx, _ = _onnx_api()
    """Export tree [N,32] or GRU [N,T,32] classifier to [N,3]."""
    _validate_model_class_order(model)
    if (family_spec(family) or {}).get("role") == "temporal":
        return _export_temporal(model,path,n_features)
    initial = _initial_types_for_family(family, n_features)

    if family == "random_forest":
        from skl2onnx import convert_sklearn
        proto = convert_sklearn(
            model,
            initial_types=initial,
            target_opset=TARGET_OPSET,
            options={id(model): {"zipmap": False, "output_class_labels": False}},
        )
    elif family == "xgboost":
        from onnxmltools import convert_xgboost
        proto = convert_xgboost(
            model,
            initial_types=initial,
            target_opset=TARGET_OPSET,
        )
    elif family == "lightgbm":
        from onnxmltools import convert_lightgbm
        # Critical: default zipmap=True produces a map output, unusable by MQL5 vectorf.
        proto = convert_lightgbm(
            model,
            initial_types=initial,
            target_opset=TARGET_OPSET,
            zipmap=False,
        )
    else:
        raise ValueError(f"Unsupported deployable family: {family}")

    proto = _probability_only(proto)
    onnx.checker.check_model(proto)
    inspect_onnx_contract(proto, n_features)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: never leave a half-written challenger.onnx behind.
    tmp = path.with_suffix(path.suffix + ".tmp")
    onnx.save(proto, tmp)
    onnx.checker.check_model(onnx.load(tmp))
    tmp.replace(path)
    return path


def verify_onnx(path, model, X, max_rows=1000, n_features: int = 32):
    import onnxruntime as ort

    _validate_model_class_order(model)
    Xs = np.asarray(X[:max_rows], dtype=np.float32)
    if Xs.ndim != 2 or Xs.shape[1] != n_features:
        raise RuntimeError(f"Parity source input must be [N,{n_features}], got {Xs.shape}")
    if not np.isfinite(Xs).all(): raise RuntimeError("Parity input contains NaN/Inf")
    runtime_X = np.asarray(model.onnx_input(Xs),dtype=np.float32) if hasattr(model,"onnx_input") else Xs

    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    if len(sess.get_inputs()) != 1 or len(sess.get_outputs()) != 1:
        raise RuntimeError(
            f"Runtime contract expected 1 input/1 output, got {len(sess.get_inputs())}/{len(sess.get_outputs())}"
        )
    inp = sess.get_inputs()[0]
    out = sess.get_outputs()[0]
    if inp.type != "tensor(float)":
        raise RuntimeError(f"ONNX Runtime input dtype must be tensor(float), got {inp.type}")
    if out.type != "tensor(float)":
        raise RuntimeError(f"ONNX Runtime output dtype must be tensor(float), got {out.type}")

    if runtime_X.ndim == 3:
        # EA contract is fixed batch=1 for sequence models; verify the exact runtime path.
        seq_out=[]
        for i in range(len(runtime_X)):
            seq_out.append(np.asarray(sess.run(None,{inp.name:runtime_X[i:i+1]})[0],dtype=np.float64))
        onnx_p=np.vstack(seq_out) if seq_out else np.empty((0,3),dtype=np.float64)
    else:
        onnx_p=np.asarray(sess.run(None,{inp.name:runtime_X})[0],dtype=np.float64)
    native_p = np.asarray(model.predict_proba(Xs), dtype=np.float64)

    expected_shape = (len(Xs), 3)
    if onnx_p.shape != expected_shape:
        raise RuntimeError(f"ONNX runtime output must be {expected_shape}, got {onnx_p.shape}")
    if native_p.shape != expected_shape:
        raise RuntimeError(f"Native probability output must be {expected_shape}, got {native_p.shape}")
    if not np.isfinite(onnx_p).all():
        raise RuntimeError("ONNX probabilities contain NaN/Inf")
    row_sum_err = float(np.max(np.abs(onnx_p.sum(axis=1) - 1.0))) if len(Xs) else 0.0
    if row_sum_err > 1e-3:
        raise RuntimeError(f"ONNX probability rows do not sum to 1; max error={row_sum_err:.8g}")

    err = float(np.max(np.abs(onnx_p - native_p))) if len(Xs) else 0.0
    return {
        "rows": int(len(Xs)),
        "runtime_batch_size": 1 if runtime_X.ndim == 3 else None,
        "batch_contract": "FIXED_1" if runtime_X.ndim == 3 else "TABULAR_DYNAMIC",
        "max_abs_error": err,
        "max_probability_sum_error": row_sum_err,
        "onnx_shape": list(onnx_p.shape),
        "classes": [0, 1, 2],
    }


def preflight_export_stack(
    families=("xgboost", "lightgbm", "random_forest", "gru", "tcn", "lstm", "transformer", "hybrid::gru::xgboost", "hybrid::tcn::lightgbm"),
    n_features: int = 32,
    tolerance: float = 1e-4,
    progress=None,
):
    """Run real synthetic conversion+ORT parity for every enabled deployable family.

    Returns a report even when one family fails, so the caller can persist evidence
    before refusing expensive research.
    """
    rng = np.random.default_rng(20260908)
    X = rng.normal(size=(90, n_features)).astype(np.float32)
    y = np.tile(np.array([0, 1, 2], dtype=np.int64), 30)
    report = {
        "status": "PASS",
        "versions": converter_stack_versions(),
        "contract": {"tabular_input": [None, n_features], "gru_input": [1, "T", n_features], "gru_batch_contract": "FIXED_1", "output": [None, 3], "classes": [0, 1, 2]},
        "families": [],
    }

    with tempfile.TemporaryDirectory(prefix="cp_onnx_preflight_") as td:
        td = Path(td)
        fams = list(families)
        total = max(1, len(fams))
        for idx, family in enumerate(fams, start=1):
            if progress:
                progress({"family": family, "current": idx-1, "total": total, "phase": "start"})
            row = {"family": family, "status": "FAIL"}
            try:
                if family == "xgboost":
                    from xgboost import XGBClassifier
                    model = XGBClassifier(
                        n_estimators=5,
                        max_depth=2,
                        learning_rate=0.15,
                        objective="multi:softprob",
                        num_class=3,
                        eval_metric="mlogloss",
                        tree_method="hist",
                        n_jobs=1,
                        random_state=7,
                    )
                elif family == "lightgbm":
                    from lightgbm import LGBMClassifier
                    model = LGBMClassifier(
                        n_estimators=5,
                        num_leaves=7,
                        max_depth=3,
                        learning_rate=0.15,
                        objective="multiclass",
                        num_class=3,
                        n_jobs=1,
                        random_state=7,
                        verbosity=-1,
                    )
                elif family == "random_forest":
                    from sklearn.ensemble import RandomForestClassifier
                    model = RandomForestClassifier(n_estimators=10,max_depth=3,n_jobs=1,random_state=7,class_weight="balanced_subsample")
                elif (family_spec(family) or {}).get("role") == "temporal":
                    if family == "gru":
                        from research.gru_research import GRUClassifier
                        model = GRUClassifier(sequence_length=8,hidden_size=16,num_layers=1,dropout=0.0,learning_rate=0.002,batch_size=64,epochs=2,weight_decay=0.0,patience=1,random_state=7,threads=1)
                    else:
                        from research.temporal_research import TemporalClassifier
                        kwargs=dict(architecture=family,sequence_length=8,hidden_size=16,num_layers=1,dropout=0.0,learning_rate=0.002,batch_size=64,epochs=2,weight_decay=0.0,patience=1,random_state=7,threads=1)
                        if family=="tcn": kwargs.update(tcn_channels=16,tcn_blocks=2,kernel_size=3)
                        if family=="transformer": kwargs.update(d_model=16,attention_heads=2,ffn_mult=2)
                        model=TemporalClassifier(**kwargs)
                elif is_hybrid_family(family):
                    from research.hybrid_research import HybridStackClassifier
                    temporal_family, policy_family = hybrid_parts(family)
                    model = HybridStackClassifier(
                        policy_family,temporal_family=temporal_family,random_state=7,threads=1,patience=1,
                        temporal_sequence_length=8,temporal_hidden_size=12,temporal_num_layers=1,temporal_dropout=0.0,
                        temporal_learning_rate=0.002,temporal_batch_size=64,temporal_epochs=2,temporal_weight_decay=0.0,
                        temporal_tcn_channels=12,temporal_tcn_blocks=2,temporal_kernel_size=3,
                        temporal_d_model=12,temporal_attention_heads=2,temporal_ffn_mult=2,
                        policy_n_estimators=10,policy_max_depth=3,policy_learning_rate=0.12,
                        policy_min_child_weight=1.0,policy_subsample=0.9,policy_colsample_bytree=0.9,
                        policy_num_leaves=7,policy_min_child_samples=10,policy_min_samples_leaf=2,policy_max_features=0.7,
                    )
                else:
                    row["error"] = "unsupported family"
                    report["families"].append(row)
                    report["status"] = "FAIL"
                    continue

                # More rows for hybrid OOF stacking; ordinary families use the same synthetic authority.
                fitX, fity = X, y
                if is_hybrid_family(family):
                    fitX=np.tile(X,(3,1)); fity=np.tile(y,3)
                model.fit(fitX, fity)
                if is_hybrid_family(family):
                    paths=export_hybrid(model,td,prefix=family,n_features=n_features)
                    cut=max(32,len(fitX)//2)
                    parity=verify_hybrid_onnx(paths,model,fitX[:cut],fitX[cut:],max_rows=min(120,len(fitX)-cut),n_features=n_features)
                else:
                    out = td / f"{filesystem_safe_id(family)}.onnx"
                    export_tabular(model, family, out, n_features)
                    parity = verify_onnx(out, model, fitX, max_rows=len(fitX), n_features=n_features)
                err = float(parity["max_abs_error"])
                if not np.isfinite(err) or err > tolerance:
                    raise RuntimeError(
                        f"max_abs_error={err:.8g} > tolerance={tolerance}"
                    )
                row.update({"status": "PASS", **parity})
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                report["status"] = "FAIL"
            report["families"].append(row)
            if progress:
                progress({"family": family, "current": idx, "total": total, "phase": "done", "status": row.get("status"), "error": row.get("error")})

    return report



def _export_direction_gru(direction_model, path: str | Path, n_features: int = 32):
    import torch
    seq_len=int(direction_model.sequence_length)
    module=copy.deepcopy(direction_model.export_module()).cpu().eval()
    dummy=torch.zeros((1,seq_len,n_features),dtype=torch.float32)
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    _torch_export_fixed_batch_one(module,dummy,tmp,'direction_probabilities')
    proto=onnx.load(tmp); onnx.checker.check_model(proto)
    if len(proto.graph.input)!=1 or len(proto.graph.output)!=1:
        raise RuntimeError('Hybrid temporal ONNX must expose 1 input / 1 output')
    idims=proto.graph.input[0].type.tensor_type.shape.dim
    if len(idims)!=3 or not idims[0].HasField('dim_value') or int(idims[0].dim_value)!=1:
        raise RuntimeError('Hybrid temporal ONNX input must be fixed batch=1 [1,T,F]')
    if idims[1].HasField('dim_value') and int(idims[1].dim_value)!=seq_len:
        raise RuntimeError(f'Hybrid temporal ONNX sequence length mismatch: {idims[1].dim_value} != {seq_len}')
    if idims[2].HasField('dim_value') and int(idims[2].dim_value)!=n_features:
        raise RuntimeError(f'Hybrid temporal ONNX feature count mismatch: {idims[2].dim_value} != {n_features}')
    od=proto.graph.output[0].type.tensor_type.shape.dim
    if len(od)!=2 or (od[1].HasField('dim_value') and od[1].dim_value!=2):
        raise RuntimeError('Hybrid temporal ONNX output must be [N,2] DOWN/UP')
    tmp.replace(path); return path


def export_hybrid(model, out_dir: str | Path, prefix: str='challenger', n_features: int=32):
    """Export leakage-safe hybrid as two explicit runtime models.

    temporal: [1,T,32] -> [1,2] DOWN/UP
    policy:   [1,36]   -> [1,3] SELL/SKIP/BUY
    """
    from research.hybrid_research import HYBRID_INPUT_FEATURES
    if model.direction_model_ is None or model.policy_model_ is None:
        raise RuntimeError('Hybrid model is not fitted')
    out_dir=Path(out_dir); out_dir.mkdir(parents=True,exist_ok=True)
    # Canonical family IDs can contain Windows-invalid characters (notably ':'
    # in dynamic hybrid IDs like hybrid::gru::lightgbm). Preserve the canonical
    # ID everywhere except the filesystem artifact name.
    safe_prefix=filesystem_safe_id(prefix)
    temporal=out_dir/f'{safe_prefix}_temporal.onnx'
    policy=out_dir/f'{safe_prefix}_policy_model.onnx'
    _export_direction_gru(model.direction_model_,temporal,n_features)
    export_tabular(model.policy_model_,model.policy_family,policy,HYBRID_INPUT_FEATURES)
    return {'temporal':temporal,'policy':policy}


def verify_hybrid_onnx(paths: dict, model, history_X, target_X, max_rows=1000, n_features: int=32):
    import onnxruntime as ort
    from research.hybrid_research import augment_policy_features
    history=np.asarray(history_X,dtype=np.float32)
    target=np.asarray(target_X[:max_rows],dtype=np.float32)
    if target.ndim!=2 or target.shape[1]!=n_features:
        raise RuntimeError(f'Hybrid parity target must be [N,{n_features}], got {target.shape}')
    temporal_input=model.direction_model_.onnx_input_with_context(history,target)
    t_sess=ort.InferenceSession(str(paths['temporal']),providers=['CPUExecutionProvider'])
    ti=t_sess.get_inputs()[0]
    t_rows=[]
    for i in range(len(temporal_input)):
        t_rows.append(np.asarray(t_sess.run(None,{ti.name:temporal_input[i:i+1]})[0],dtype=np.float64))
    onnx_dir=np.vstack(t_rows) if t_rows else np.empty((0,2),dtype=np.float64)
    native_dir=np.asarray(model.direction_model_.predict_proba_with_context(history,target),dtype=np.float64)
    if onnx_dir.shape!=(len(target),2): raise RuntimeError(f'Hybrid temporal shape {onnx_dir.shape}')
    dir_err=float(np.max(np.abs(onnx_dir-native_dir))) if len(target) else 0.0
    policy_X=augment_policy_features(target,onnx_dir)
    p_sess=ort.InferenceSession(str(paths['policy']),providers=['CPUExecutionProvider'])
    pi=p_sess.get_inputs()[0]
    onnx_p=np.asarray(p_sess.run(None,{pi.name:policy_X})[0],dtype=np.float64)
    native_p=np.asarray(model.predict_proba_with_context(history,target),dtype=np.float64)
    if onnx_p.shape!=(len(target),3): raise RuntimeError(f'Hybrid policy shape {onnx_p.shape}')
    if not np.isfinite(onnx_p).all(): raise RuntimeError('Hybrid ONNX probabilities contain NaN/Inf')
    row_sum_err=float(np.max(np.abs(onnx_p.sum(axis=1)-1.0))) if len(target) else 0.0
    policy_err=float(np.max(np.abs(onnx_p-native_p))) if len(target) else 0.0
    return {
      'rows':int(len(target)),'runtime_batch_size':1,'batch_contract':'FIXED_1','max_abs_error':max(dir_err,policy_err),'temporal_max_abs_error':dir_err,
      'policy_max_abs_error':policy_err,'max_probability_sum_error':row_sum_err,
      'temporal_shape':list(onnx_dir.shape),'onnx_shape':list(onnx_p.shape),'classes':[0,1,2],
      'runtime_schema':'CP_HYBRID_TEMPORAL_POLICY_V1'
    }


def verify_onnx_with_context(path, model, history_X, target_X, max_rows=1000, n_features: int=32):
    """Exact standalone temporal-model parity with causal history before target rows."""
    import onnxruntime as ort
    target=np.asarray(target_X[:max_rows],dtype=np.float32)
    history=np.asarray(history_X,dtype=np.float32)
    runtime_X=np.asarray(model.onnx_input_with_context(history,target),dtype=np.float32)
    sess=ort.InferenceSession(str(path),providers=['CPUExecutionProvider'])
    inp=sess.get_inputs()[0]
    rows=[]
    for i in range(len(runtime_X)):
        rows.append(np.asarray(sess.run(None,{inp.name:runtime_X[i:i+1]})[0],dtype=np.float64))
    onnx_p=np.vstack(rows) if rows else np.empty((0,3),dtype=np.float64)
    native_p=np.asarray(model.predict_proba_with_context(history,target),dtype=np.float64)
    if onnx_p.shape!=(len(target),3): raise RuntimeError(f'Temporal context ONNX shape {onnx_p.shape}')
    err=float(np.max(np.abs(onnx_p-native_p))) if len(target) else 0.0
    row_sum_err=float(np.max(np.abs(onnx_p.sum(axis=1)-1.0))) if len(target) else 0.0
    return {'rows':int(len(target)),'runtime_batch_size':1,'batch_contract':'FIXED_1','max_abs_error':err,'max_probability_sum_error':row_sum_err,'onnx_shape':list(onnx_p.shape),'classes':[0,1,2],'runtime_schema':'CP32_SEQUENCE_CAUSAL_V2'}

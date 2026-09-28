from __future__ import annotations

# Dedicated child for Scientist analytical code.  Generated code is never given raw
# scientific module objects: imports resolve to deterministic capability proxies whose
# outputs are primitive JSON values or guarded in-memory wrappers.  This is a guarded
# executor/capability boundary, not a claim of OS-level sandboxing.
import contextlib
import io
import json
import random
import sys
import traceback
from pathlib import Path as _HostPath

# -I intentionally ignores ambient PYTHONPATH; add only this trusted source directory so
# the child can load the shared static capability contract. Generated code never receives sys/pathlib.
sys.path.insert(0, str(_HostPath(__file__).resolve().parents[2]))

from scientist.python.scientist_python_capabilities import ALLOWED_IMPORTS, SAFE_IMPORT_SURFACE

_REAL: dict[str, object] = {}
_IMPORT_PROXIES: dict[str, object] = {}


def _load_real_modules() -> None:
    # Raw modules remain private to this trusted child implementation.  They are loaded
    # before Python-level defense-in-depth guards because imports themselves may need
    # filesystem access.  Missing scientific packages are tolerated for acceptance-only
    # fixtures and will make that capability import fail closed.
    import importlib
    for name in sorted(ALLOWED_IMPORTS):
        try:
            _REAL[name] = importlib.import_module(name)
        except Exception:
            pass


def _install_runtime_guards() -> None:
    # Defense in depth.  The primary boundary is the capability surface: generated code
    # never receives these modules.  These patches additionally block common accidental
    # or library-mediated Python-level filesystem/process/network/thread actions.
    import builtins as _builtins
    import io as _io
    import multiprocessing as _multiprocessing
    import os as _os
    import pathlib as _pathlib
    import shutil as _shutil
    import socket as _socket
    import subprocess as _subprocess
    import tempfile as _tempfile
    import threading as _threading

    def blocked(*args, **kwargs):
        raise PermissionError("Scientist Python capability runtime blocks filesystem/process/network/thread authority")

    _builtins.open = blocked
    _io.open = blocked
    for name in (
        "open", "system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve",
        "spawnvp", "spawnvpe", "execv", "execve", "execvp", "execvpe", "remove", "unlink", "rename",
        "replace", "mkdir", "makedirs", "rmdir", "chdir",
    ):
        if hasattr(_os, name):
            setattr(_os, name, blocked)
    for name in ("copy", "copy2", "copyfile", "copytree", "move", "rmtree", "make_archive", "unpack_archive"):
        if hasattr(_shutil, name):
            setattr(_shutil, name, blocked)
    for name in ("open", "read_text", "read_bytes", "write_text", "write_bytes", "unlink", "rename", "replace", "mkdir", "rmdir", "touch"):
        if hasattr(_pathlib.Path, name):
            setattr(_pathlib.Path, name, blocked)
    for name in ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
        if hasattr(_subprocess, name):
            setattr(_subprocess, name, blocked)
    for name in ("socket", "socketpair", "create_connection", "fromfd"):
        if hasattr(_socket, name):
            setattr(_socket, name, blocked)
    for name in ("NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile", "TemporaryDirectory", "mkstemp", "mkdtemp"):
        if hasattr(_tempfile, name):
            setattr(_tempfile, name, blocked)
    try:
        _multiprocessing.Process.start = blocked
    except Exception:
        pass
    try:
        _threading.Thread.start = blocked
    except Exception:
        pass


def _unwrap(value):
    if isinstance(value, _SafeArray):
        return object.__getattribute__(value, "_value")
    if isinstance(value, _SafeSeries):
        return object.__getattribute__(value, "_value")
    if isinstance(value, _SafeDataFrame):
        return object.__getattribute__(value, "_value")
    if isinstance(value, (list, tuple)):
        return type(value)(_unwrap(x) for x in value)
    if isinstance(value, dict):
        return {k: _unwrap(v) for k, v in value.items()}
    return value


def _reject_generated_callables(value, *, label: str = "argument") -> None:
    """Never let a real scientific library call back into generated Scientist code.

    Capability functions may accept primitives and guarded wrappers only. Passing Python
    functions/lambdas as callbacks would let pandas/scipy/sklearn invoke generated code
    while holding raw internal objects, reopening a transitive authority channel.
    """
    if callable(value) and not isinstance(value, _SafeCallable):
        raise PermissionError(f"Scientist callable callback not allowed: {label}")
    if isinstance(value, dict):
        for k, v in value.items():
            _reject_generated_callables(k, label=label)
            _reject_generated_callables(v, label=label)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _reject_generated_callables(item, label=label)


def _approved_kwargs(kwargs, allowed: set[str], *, label: str) -> dict:
    _reject_generated_callables(kwargs, label=label)
    unexpected = sorted(str(k) for k in kwargs if str(k) not in allowed)
    if unexpected:
        raise PermissionError(f"Scientist capability keyword not allowed for {label}: {', '.join(unexpected)}")
    return {str(k): _unwrap(v) for k, v in kwargs.items()}


def _safe_agg_spec(value):
    allowed = {"mean", "median", "sum", "min", "max", "std", "count", "size"}
    _reject_generated_callables(value, label="aggregation")
    if isinstance(value, str):
        if value not in allowed:
            raise PermissionError(f"aggregation not allowed: {value}")
        return value
    if isinstance(value, (list, tuple)):
        return type(value)(_safe_agg_spec(v) for v in value)
    if isinstance(value, dict):
        return {str(k): _safe_agg_spec(v) for k, v in value.items()}
    raise PermissionError("aggregation spec must use approved string operations")


def _scalar(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[:2000]
    if hasattr(value, "item"):
        try:
            item = value.item()
            if item is value:
                return str(value)[:2000]
            return _scalar(item)
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return str(value.isoformat())
        except Exception:
            pass
    # Fail closed on unfamiliar library scalar/object types: generated code receives a
    # bounded textual representation, never the raw object or its methods.
    return str(value)[:2000]


def _plain_stat(value):
    if isinstance(value, _SafeArray):
        return value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _plain_stat(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        # SciPy named result tuples become deterministic dictionaries where practical.
        fields = getattr(type(value), "_fields", None)
        if fields:
            return {str(k): _plain_stat(v) for k, v in zip(fields, value)}
        return [_plain_stat(v) for v in value]
    if hasattr(value, "shape") and hasattr(value, "tolist"):
        return _SafeArray(value)
    return _scalar(value)


class _SafeCallable:
    __slots__ = ("_fn", "_name")

    def __init__(self, name, fn):
        object.__setattr__(self, "_fn", fn)
        object.__setattr__(self, "_name", str(name))

    def __call__(self, *args, **kwargs):
        fn = object.__getattribute__(self, "_fn")
        return fn(*args, **kwargs)

    def __getattribute__(self, name):
        if name in {"__call__", "__repr__"}:
            return object.__getattribute__(self, name)
        raise AttributeError("capability callables expose no attributes")

    def __repr__(self):
        return f"<ScientistCapability {object.__getattribute__(self, '_name')}>"


class _ModuleProxy:
    __slots__ = ("_name", "_attrs")

    def __init__(self, name: str, attrs: dict[str, object]):
        object.__setattr__(self, "_name", str(name))
        object.__setattr__(self, "_attrs", dict(attrs))

    def __getattribute__(self, name):
        if name == "__repr__":
            return object.__getattribute__(self, name)
        if name.startswith("_"):
            raise AttributeError("private capability state is not exposed")
        attrs = object.__getattribute__(self, "_attrs")
        if name not in attrs:
            raise AttributeError(f"Scientist capability attribute not exposed: {name}")
        return attrs[name]

    def __repr__(self):
        return f"<ScientistCapabilityModule {object.__getattribute__(self, '_name')}>"


class _SafeArray:
    __slots__ = ("_value",)

    def __init__(self, value):
        np = _REAL.get("numpy")
        if np is None:
            raise RuntimeError("NumPy capability unavailable")
        object.__setattr__(self, "_value", np.asarray(_unwrap(value)))

    def _a(self):
        return object.__getattribute__(self, "_value")

    def __getattribute__(self, name):
        if name.startswith("_"):
            raise AttributeError("private array state is not exposed")
        a = object.__getattribute__(self, "_value")
        np = _REAL["numpy"]
        values = {
            "shape": tuple(int(x) for x in a.shape), "size": int(a.size), "ndim": int(a.ndim), "dtype": str(a.dtype),
        }
        if name in values:
            return values[name]
        funcs = {
            "tolist": lambda: a.tolist(), "to_list": lambda: a.tolist(),
            "mean": lambda: _scalar(np.mean(a)), "median": lambda: _scalar(np.median(a)),
            "std": lambda *args, **kwargs: _scalar(np.std(a, *args, **kwargs)),
            "var": lambda *args, **kwargs: _scalar(np.var(a, *args, **kwargs)),
            "sum": lambda *args, **kwargs: _scalar(np.sum(a, *args, **kwargs)),
            "min": lambda *args, **kwargs: _scalar(np.min(a, *args, **kwargs)),
            "max": lambda *args, **kwargs: _scalar(np.max(a, *args, **kwargs)),
            "quantile": lambda q, *args, **kwargs: _plain_stat(np.quantile(a, q, *args, **kwargs)),
            "reshape": lambda *shape: _SafeArray(a.reshape(*shape)),
            "flatten": lambda: _SafeArray(a.flatten()), "ravel": lambda: _SafeArray(a.ravel()),
            "astype": lambda dtype: _SafeArray(a.astype(str(dtype))),
        }
        if name in funcs:
            return _SafeCallable(f"array.{name}", funcs[name])
        raise AttributeError(f"Scientist array attribute not exposed: {name}")

    def __len__(self): return len(object.__getattribute__(self, "_value"))
    def __iter__(self):
        for v in object.__getattribute__(self, "_value"):
            yield _SafeArray(v) if hasattr(v, "shape") and getattr(v, "ndim", 0) else _scalar(v)
    def __getitem__(self, key):
        v = object.__getattribute__(self, "_value")[key]
        return _SafeArray(v) if hasattr(v, "shape") and getattr(v, "ndim", 0) else _scalar(v)
    def _bin(self, other, op): return _SafeArray(op(object.__getattribute__(self, "_value"), _unwrap(other)))
    def __add__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a+b)
    def __radd__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:b+a)
    def __sub__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a-b)
    def __rsub__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:b-a)
    def __mul__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a*b)
    def __rmul__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:b*a)
    def __truediv__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a/b)
    def __rtruediv__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:b/a)
    def __pow__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a**b)
    def __neg__(self): return _SafeArray(-object.__getattribute__(self, "_value"))
    def __eq__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a==b)
    def __ne__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a!=b)
    def __lt__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a<b)
    def __le__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a<=b)
    def __gt__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a>b)
    def __ge__(self, o): return object.__getattribute__(self,"_bin")(o, lambda a,b:a>=b)
    def __repr__(self): return f"SafeArray({object.__getattribute__(self, '_value')!r})"


class _SafeSeries:
    __slots__ = ("_value",)
    def __init__(self, value):
        pd = _REAL.get("pandas")
        if pd is None: raise RuntimeError("pandas capability unavailable")
        object.__setattr__(self, "_value", value.copy() if value.__class__.__name__ == "Series" else pd.Series(_unwrap(value)))
    def __getattribute__(self, name):
        if name.startswith("_"): raise AttributeError("private series state is not exposed")
        s=object.__getattribute__(self,"_value")
        funcs={
            "tolist":lambda:_plain_stat(s.tolist()), "to_list":lambda:_plain_stat(s.tolist()), "to_dict":lambda:_plain_stat(s.to_dict()),
            "head":lambda n=5:_SafeSeries(s.head(int(n))), "tail":lambda n=5:_SafeSeries(s.tail(int(n))),
            "sort_values":lambda **k:object.__getattribute__(self,"_sort_values")(k), "dropna":lambda:_SafeSeries(s.dropna()),
            "fillna":lambda v:_SafeSeries(s.fillna(_unwrap(v))), "mean":lambda:_scalar(s.mean()), "median":lambda:_scalar(s.median()),
            "std":lambda:_scalar(s.std()), "sum":lambda:_scalar(s.sum()), "min":lambda:_scalar(s.min()), "max":lambda:_scalar(s.max()),
            "quantile":lambda q:_scalar(s.quantile(q)), "nunique":lambda:int(s.nunique()), "unique":lambda:_SafeArray(s.unique()),
            "value_counts":lambda:_SafeSeries(s.value_counts()), "corr":lambda other:_scalar(s.corr(_unwrap(other))),
            "to_numpy":lambda:_SafeArray(s.to_numpy()),
        }
        if name in funcs: return _SafeCallable(f"series.{name}",funcs[name])
        raise AttributeError(f"Scientist series attribute not exposed: {name}")
    def _sort_values(self, kw):
        opts=_approved_kwargs(kw,{"ascending","na_position","ignore_index"},label="Series.sort_values")
        return _SafeSeries(object.__getattribute__(self,"_value").sort_values(**opts))
    def __len__(self): return len(object.__getattribute__(self,"_value"))
    def __iter__(self):
        for v in object.__getattribute__(self,"_value"): yield _scalar(v)
    def __getitem__(self,k):
        v = object.__getattribute__(self,"_value").iloc[k] if isinstance(k,int) else object.__getattribute__(self,"_value")[k]
        if v.__class__.__name__ == "Series": return _SafeSeries(v)
        if hasattr(v, "shape") and hasattr(v, "tolist") and getattr(v, "ndim", 0): return _SafeArray(v)
        return _scalar(v)
    def _bin(self,o,op): return _SafeSeries(op(object.__getattribute__(self,"_value"),_unwrap(o)))
    def __add__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a+b)
    def __sub__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a-b)
    def __mul__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a*b)
    def __truediv__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a/b)
    def __eq__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a==b)
    def __ne__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a!=b)
    def __gt__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a>b)
    def __ge__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a>=b)
    def __lt__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a<b)
    def __le__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a<=b)
    def __and__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a & b)
    def __or__(self,o): return object.__getattribute__(self,"_bin")(o,lambda a,b:a | b)
    def __invert__(self): return _SafeSeries(~object.__getattribute__(self,"_value"))
    def __repr__(self): return "SafeSeries(<in-memory>)"


class _SafeGroupBy:
    __slots__=("_value",)
    def __init__(self,value): object.__setattr__(self,"_value",value)
    def __getattribute__(self,name):
        if name.startswith("_"): raise AttributeError("private groupby state is not exposed")
        g=object.__getattribute__(self,"_value")
        funcs={
            "mean":lambda:_SafeDataFrame(g.mean(numeric_only=True).reset_index()),
            "median":lambda:_SafeDataFrame(g.median(numeric_only=True).reset_index()),
            "sum":lambda:_SafeDataFrame(g.sum(numeric_only=True).reset_index()),
            "agg":lambda spec:_SafeDataFrame(g.agg(_safe_agg_spec(spec)).reset_index()),
        }
        if name in funcs:return _SafeCallable(f"groupby.{name}",funcs[name])
        raise AttributeError(f"Scientist groupby attribute not exposed: {name}")


class _SafeDataFrame:
    __slots__=("_value",)
    def __init__(self,value):
        pd=_REAL.get("pandas")
        if pd is None: raise RuntimeError("pandas capability unavailable")
        object.__setattr__(self,"_value",value.copy() if value.__class__.__name__=="DataFrame" else pd.DataFrame(_unwrap(value)))
    def __getattribute__(self,name):
        if name.startswith("_"): raise AttributeError("private dataframe state is not exposed")
        df=object.__getattribute__(self,"_value")
        funcs={
            "head":lambda n=5:_SafeDataFrame(df.head(int(n))), "tail":lambda n=5:_SafeDataFrame(df.tail(int(n))),
            "to_dict":lambda orient="records":_plain_stat(df.to_dict(orient=str(orient))), "to_numpy":lambda:_SafeArray(df.to_numpy()),
            "sort_values":lambda by,**k:object.__getattribute__(self,"_sort_values")(by,k),
            "dropna":lambda:_SafeDataFrame(df.dropna()), "fillna":lambda v:_SafeDataFrame(df.fillna(_unwrap(v))),
            "assign":lambda **kw:object.__getattribute__(self,"_assign")(kw),
            "describe":lambda:_SafeDataFrame(df.describe().reset_index()),
            "mean":lambda:_SafeSeries(df.mean(numeric_only=True)), "median":lambda:_SafeSeries(df.median(numeric_only=True)),
            "std":lambda:_SafeSeries(df.std(numeric_only=True)), "sum":lambda:_SafeSeries(df.sum(numeric_only=True)),
            "corr":lambda:_SafeDataFrame(df.corr(numeric_only=True)),
            "groupby":lambda by:object.__getattribute__(self,"_groupby")(by),
        }
        if name in funcs:return _SafeCallable(f"dataframe.{name}",funcs[name])
        raise AttributeError(f"Scientist dataframe attribute not exposed: {name}")
    def _sort_values(self, by, kw):
        _reject_generated_callables(by,label="DataFrame.sort_values")
        if not isinstance(by,(str,list,tuple)) or (isinstance(by,(list,tuple)) and not all(isinstance(x,str) for x in by)):
            raise PermissionError("sort_values 'by' must be column name(s)")
        opts=_approved_kwargs(kw,{"ascending","na_position","ignore_index"},label="DataFrame.sort_values")
        return _SafeDataFrame(object.__getattribute__(self,"_value").sort_values(by=by,**opts))
    def _assign(self, kw):
        _reject_generated_callables(kw, label="DataFrame.assign")
        df=object.__getattribute__(self,"_value")
        return _SafeDataFrame(df.assign(**{k:_unwrap(v) for k,v in kw.items()}))
    def _groupby(self, by):
        _reject_generated_callables(by, label="DataFrame.groupby")
        if not isinstance(by, (str, list, tuple)):
            raise PermissionError("groupby key must be a column name or list of column names")
        if isinstance(by, (list, tuple)) and not all(isinstance(x, str) for x in by):
            raise PermissionError("groupby keys must be column names")
        return _SafeGroupBy(object.__getattribute__(self,"_value").groupby(by))
    def __len__(self): return len(object.__getattribute__(self,"_value"))
    def __getitem__(self,key):
        # Trusted, type-restricted indexing boundary. Generated Scientist code never
        # receives a raw pandas object or a generic unwrap capability. Only explicitly
        # supported governed key types are converted internally.
        df=object.__getattribute__(self,"_value")
        pd=_REAL.get("pandas")
        if isinstance(key,str):
            v=df[key]
        elif isinstance(key,(list,tuple)) and all(isinstance(x,str) for x in key):
            v=df[list(key)]
        elif type(key) is _SafeSeries:
            mask=object.__getattribute__(key,"_value")
            if pd is None or not bool(pd.api.types.is_bool_dtype(mask.dtype)):
                raise PermissionError("DataFrame governed Series index must be boolean")
            v=df[mask]
        elif type(key) is _SafeArray:
            mask=object.__getattribute__(key,"_value")
            if pd is None or not bool(pd.api.types.is_bool_dtype(mask.dtype)):
                raise PermissionError("DataFrame governed array index must be boolean")
            v=df[mask]
        else:
            raise PermissionError("DataFrame index key type is not an approved Scientist capability")
        if v.__class__.__name__=="DataFrame":
            return _SafeDataFrame(v)
        if v.__class__.__name__=="Series":
            return _SafeSeries(v)
        return _scalar(v)
    def __setitem__(self,key,value): object.__getattribute__(self,"_value")[key]=_unwrap(value)
    def __repr__(self): return "SafeDataFrame(<in-memory>)"


class _SafeLinearRegression:
    __slots__=("_model",)
    def __init__(self,**kwargs):
        mod=_REAL.get("sklearn.linear_model")
        if mod is None: raise RuntimeError("sklearn linear_model capability unavailable")
        # n_jobs is intentionally not exposed.
        object.__setattr__(self,"_model",mod.LinearRegression(**{k:v for k,v in kwargs.items() if k in {"fit_intercept","positive"}}))
    def __getattribute__(self,name):
        if name.startswith("_"): raise AttributeError("private estimator state is not exposed")
        m=object.__getattribute__(self,"_model")
        if name=="fit": return _SafeCallable("LinearRegression.fit",lambda X,y:object.__getattribute__(self,"_fit")(X,y))
        if name=="predict": return _SafeCallable("LinearRegression.predict",lambda X:_SafeArray(m.predict(_unwrap(X))))
        if name=="score": return _SafeCallable("LinearRegression.score",lambda X,y:float(m.score(_unwrap(X),_unwrap(y))))
        if name=="coef_": return _SafeArray(m.coef_)
        if name=="intercept_": return _plain_stat(m.intercept_)
        raise AttributeError(f"Scientist estimator attribute not exposed: {name}")
    def _fit(self,X,y): object.__getattribute__(self,"_model").fit(_unwrap(X),_unwrap(y)); return self


class _SafeStandardScaler:
    __slots__=("_model",)
    def __init__(self,**kwargs):
        mod=_REAL.get("sklearn.preprocessing")
        if mod is None: raise RuntimeError("sklearn preprocessing capability unavailable")
        object.__setattr__(self,"_model",mod.StandardScaler(**{k:v for k,v in kwargs.items() if k in {"with_mean","with_std"}}))
    def __getattribute__(self,name):
        if name.startswith("_"): raise AttributeError("private scaler state is not exposed")
        m=object.__getattribute__(self,"_model")
        if name=="fit": return _SafeCallable("StandardScaler.fit",lambda X:object.__getattribute__(self,"_fit")(X))
        if name=="transform": return _SafeCallable("StandardScaler.transform",lambda X:_SafeArray(m.transform(_unwrap(X))))
        if name=="fit_transform": return _SafeCallable("StandardScaler.fit_transform",lambda X:_SafeArray(m.fit_transform(_unwrap(X))))
        raise AttributeError(f"Scientist scaler attribute not exposed: {name}")
    def _fit(self,X): object.__getattribute__(self,"_model").fit(_unwrap(X)); return self


class _SafeKMeans:
    __slots__=("_model",)
    def __init__(self,n_clusters=8,random_state=42,**kwargs):
        mod=_REAL.get("sklearn.cluster")
        if mod is None: raise RuntimeError("sklearn cluster capability unavailable")
        object.__setattr__(self,"_model",mod.KMeans(n_clusters=int(n_clusters),random_state=int(random_state),n_init="auto"))
    def __getattribute__(self,name):
        if name.startswith("_"): raise AttributeError("private cluster state is not exposed")
        m=object.__getattribute__(self,"_model")
        if name=="fit": return _SafeCallable("KMeans.fit",lambda X:object.__getattribute__(self,"_fit")(X))
        if name=="predict": return _SafeCallable("KMeans.predict",lambda X:_SafeArray(m.predict(_unwrap(X))))
        if name=="score": return _SafeCallable("KMeans.score",lambda X:float(m.score(_unwrap(X))))
        if name=="cluster_centers_": return _SafeArray(m.cluster_centers_)
        raise AttributeError(f"Scientist cluster attribute not exposed: {name}")
    def _fit(self,X): object.__getattribute__(self,"_model").fit(_unwrap(X)); return self


def _callable(name, fn, transform=_plain_stat):
    def call(*args,**kwargs):
        _reject_generated_callables(args, label=name)
        _reject_generated_callables(kwargs, label=name)
        return transform(fn(*[_unwrap(a) for a in args],**{k:_unwrap(v) for k,v in kwargs.items()}))
    return _SafeCallable(name,call)


def _build_capabilities(seed: int) -> dict[str, object]:
    import math, statistics, json as json_module
    proxies: dict[str,object]={}
    proxies["math"]=_ModuleProxy("math",{n:_callable(f"math.{n}",getattr(math,n),_plain_stat) for n in SAFE_IMPORT_SURFACE["math"]})
    proxies["statistics"]=_ModuleProxy("statistics",{n:_callable(f"statistics.{n}",getattr(statistics,n),_plain_stat) for n in SAFE_IMPORT_SURFACE["statistics"]})
    proxies["json"]=_ModuleProxy("json",{
        "dumps":_SafeCallable("json.dumps",lambda obj,**kw:json_module.dumps(_unwrap(obj),ensure_ascii=False,**{k:v for k,v in kw.items() if k in {"sort_keys","indent"}})),
        "loads":_SafeCallable("json.loads",lambda text:json_module.loads(str(text))),
    })
    np=_REAL.get("numpy")
    if np is not None:
        np.random.seed(seed)
        def arr_fn(fn): return _SafeCallable(f"numpy.{fn.__name__}",lambda *a,**k:_plain_stat(fn(*[_unwrap(x) for x in a],**{x:_unwrap(y) for x,y in k.items()})))
        attrs={
            "array":_SafeCallable("numpy.array",lambda x,**k:_SafeArray(np.array(_unwrap(x),**_approved_kwargs(k,{"dtype"},label="numpy.array")))),
            "asarray":_SafeCallable("numpy.asarray",lambda x,**k:_SafeArray(np.asarray(_unwrap(x),**_approved_kwargs(k,{"dtype"},label="numpy.asarray")))),
        }
        for n in ("mean","median","std","var","sum","min","max","percentile","quantile","corrcoef","cov","sqrt","log","log1p","exp","abs","clip","where","isnan","isfinite","unique","argsort","argmax","argmin","concatenate","stack","vstack","hstack","linspace","arange","dot","diff","cumsum","cumprod","round","zeros","ones","full"):
            attrs[n]=arr_fn(getattr(np,n))
        random_proxy=_ModuleProxy("numpy.random",{
            "choice":_SafeCallable("numpy.random.choice",lambda *a,**k:_plain_stat(np.random.choice(*[_unwrap(x) for x in a],**{x:_unwrap(y) for x,y in k.items()}))),
            "permutation":_SafeCallable("numpy.random.permutation",lambda x:_plain_stat(np.random.permutation(_unwrap(x)))),
            "normal":_SafeCallable("numpy.random.normal",lambda *a,**k:_plain_stat(np.random.normal(*a,**k))),
            "uniform":_SafeCallable("numpy.random.uniform",lambda *a,**k:_plain_stat(np.random.uniform(*a,**k))),
            "integers":_SafeCallable("numpy.random.integers",lambda low,high=None,size=None:_plain_stat(np.random.default_rng(seed).integers(low,high,size))),
        })
        attrs["random"]=random_proxy
        proxies["numpy"]=_ModuleProxy("numpy",attrs)
    pd=_REAL.get("pandas")
    if pd is not None:
        proxies["pandas"]=_ModuleProxy("pandas",{
            "DataFrame":_SafeCallable("pandas.DataFrame",lambda data=None,**kw:_SafeDataFrame(pd.DataFrame(_unwrap(data),**_approved_kwargs(kw,{"columns"},label="pandas.DataFrame")))),
            "Series":_SafeCallable("pandas.Series",lambda data=None,**kw:_SafeSeries(pd.Series(_unwrap(data),**_approved_kwargs(kw,{"name"},label="pandas.Series")))),
        })
    st=_REAL.get("scipy.stats")
    if st is not None:
        stat_attrs={n:_callable(f"scipy.stats.{n}",getattr(st,n),_plain_stat) for n in SAFE_IMPORT_SURFACE["scipy.stats"] if hasattr(st,n)}
        stats_proxy=_ModuleProxy("scipy.stats",stat_attrs)
        proxies["scipy.stats"]=stats_proxy
        proxies["scipy"]=_ModuleProxy("scipy",{"stats":stats_proxy})
    met=_REAL.get("sklearn.metrics")
    pre=_REAL.get("sklearn.preprocessing")
    ms=_REAL.get("sklearn.model_selection")
    lm=_REAL.get("sklearn.linear_model")
    cl=_REAL.get("sklearn.cluster")
    if met is not None:
        metrics=_ModuleProxy("sklearn.metrics",{n:_callable(f"sklearn.metrics.{n}",getattr(met,n),_plain_stat) for n in SAFE_IMPORT_SURFACE["sklearn.metrics"]})
        proxies["sklearn.metrics"]=metrics
    else: metrics=None
    if pre is not None:
        preprocessing=_ModuleProxy("sklearn.preprocessing",{"StandardScaler":_SafeCallable("StandardScaler",lambda **kw:_SafeStandardScaler(**kw))})
        proxies["sklearn.preprocessing"]=preprocessing
    else: preprocessing=None
    if ms is not None:
        def split(*args,**kwargs):
            vals=ms.train_test_split(*[_unwrap(x) for x in args],**{k:_unwrap(v) for k,v in kwargs.items() if k in {"test_size","train_size","random_state","shuffle","stratify"}})
            return [_plain_stat(v) for v in vals]
        model_selection=_ModuleProxy("sklearn.model_selection",{"train_test_split":_SafeCallable("train_test_split",split)})
        proxies["sklearn.model_selection"]=model_selection
    else:model_selection=None
    if lm is not None:
        linear_model=_ModuleProxy("sklearn.linear_model",{"LinearRegression":_SafeCallable("LinearRegression",lambda **kw:_SafeLinearRegression(**kw))})
        proxies["sklearn.linear_model"]=linear_model
    else:linear_model=None
    if cl is not None:
        cluster=_ModuleProxy("sklearn.cluster",{"KMeans":_SafeCallable("KMeans",lambda **kw:_SafeKMeans(**kw))})
        proxies["sklearn.cluster"]=cluster
    else:cluster=None
    if any(x is not None for x in (metrics,preprocessing,model_selection,linear_model,cluster)):
        attrs={k:v for k,v in {"metrics":metrics,"preprocessing":preprocessing,"model_selection":model_selection,"linear_model":linear_model,"cluster":cluster}.items() if v is not None}
        proxies["sklearn"]=_ModuleProxy("sklearn",attrs)
    return proxies


def _controlled_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level:
        raise ImportError("relative imports are not allowed")
    name=str(name or "")
    if name not in ALLOWED_IMPORTS:
        raise ImportError(f"Scientist analysis import not allowed: {name}")
    proxy=_IMPORT_PROXIES.get(name)
    if proxy is None:
        raise ImportError(f"Scientist analytical capability unavailable: {name}")
    return proxy


class _BoundedText(io.TextIOBase):
    def __init__(self,limit=12000): super().__init__(); self.limit=max(0,int(limit)); self.parts=[]; self.count=0; self.truncated=False
    def write(self,value):
        text=str(value); remaining=max(0,self.limit-self.count)
        if remaining:
            piece=text[:remaining]; self.parts.append(piece); self.count+=len(piece)
        if len(text)>remaining:self.truncated=True
        return len(text)
    def getvalue(self): return "".join(self.parts)+("\n<OUTPUT_TRUNCATED>" if self.truncated else "")


_SAFE_BUILTINS={
    "abs":abs,"all":all,"any":any,"bool":bool,"dict":dict,"enumerate":enumerate,"float":float,"int":int,
    "len":len,"list":list,"max":max,"min":min,"print":print,"range":range,"reversed":reversed,"round":round,
    "set":set,"sorted":sorted,"str":str,"sum":sum,"tuple":tuple,"zip":zip,
    "Exception":Exception,"ValueError":ValueError,"TypeError":TypeError,"ZeroDivisionError":ZeroDivisionError,
    "__import__":_controlled_import,
}


def _normalize(value,depth=0):
    if depth>8:return "<MAX_DEPTH>"
    if value is None or isinstance(value,(bool,int,float,str)):return value
    if isinstance(value,_SafeArray):return _normalize(object.__getattribute__(value,"_value").tolist(),depth+1)
    if isinstance(value,_SafeSeries):return _normalize(object.__getattribute__(value,"_value").tolist(),depth+1)
    if isinstance(value,_SafeDataFrame):return _normalize(object.__getattribute__(value,"_value").head(1000).to_dict(orient="records"),depth+1)
    if isinstance(value,dict):return {str(k):_normalize(v,depth+1) for k,v in list(value.items())[:5000]}
    if isinstance(value,(list,tuple,set)):return [_normalize(v,depth+1) for v in list(value)[:5000]]
    return str(value)[:2000]


def main()->int:
    try:
        req=json.loads(sys.stdin.read()); code=str(req.get("code") or ""); inputs=req.get("inputs") if isinstance(req.get("inputs"),dict) else {}
        seed=int(req.get("seed",42)); max_result_bytes=int(req.get("max_result_bytes",512000)); random.seed(seed)
        _load_real_modules()
        global _IMPORT_PROXIES
        _IMPORT_PROXIES=_build_capabilities(seed)
        _install_runtime_guards()
        glob={"__builtins__":_SAFE_BUILTINS,"inputs":inputs,"seed":seed,"result":None}
        captured_out=_BoundedText(11000); captured_err=_BoundedText(11000)
        with contextlib.redirect_stdout(captured_out),contextlib.redirect_stderr(captured_err):
            compiled=compile(code,"<scientist_analysis>","exec")
            exec(compiled,glob,glob)
        result=_normalize(glob.get("result")); encoded=json.dumps(result,ensure_ascii=False,separators=(",",":"),default=str).encode("utf-8")
        if len(encoded)>max_result_bytes:raise ValueError(f"structured result exceeds {max_result_bytes} bytes")
        sys.stdout.write(json.dumps({"status":"EXECUTED","result":result,"captured_stdout":captured_out.getvalue()[:12000],"captured_stderr":captured_err.getvalue()[:12000]},ensure_ascii=False,separators=(",",":"),default=str)); return 0
    except Exception as exc:
        sys.stdout.write(json.dumps({"status":"ERROR","error":f"{type(exc).__name__}: {exc}","traceback_excerpt":traceback.format_exc(limit=3)[-4000:]},ensure_ascii=False,separators=(",",":"),default=str)); return 1


if __name__=="__main__":
    raise SystemExit(main())

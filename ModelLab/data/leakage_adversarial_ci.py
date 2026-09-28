from __future__ import annotations
import numpy as np, pandas as pd
from core.temporal_index import expanding_folds, purge_train_before_validation, contiguous_chunks

def future_perturbation_test(feature_fn)->dict:
    n=400; cut=260
    df=pd.DataFrame({'x':np.arange(n,dtype=float),'signal_time':pd.date_range('2020-01-01',periods=n,freq='h')})
    base=np.asarray(feature_fn(df.copy()))[:cut].copy()
    pert=df.copy(); pert.loc[cut:,'x'] += 1_000_000.0
    after=np.asarray(feature_fn(pert))[:cut]
    ok=np.array_equal(base,after,equal_nan=True)
    return {'gate':'FUTURE_PERTURBATION','passed':bool(ok)}

def label_overlap_test()->dict:
    tr=np.arange(0,200); va=np.arange(200,240); purge=12
    p=purge_train_before_validation(tr,va,purge)
    # every retained train label ending at t+purge must finish before validation begins
    ok=(len(p)>0 and int(p.max())+purge < int(va.min()))
    return {'gate':'LABEL_OVERLAP','passed':bool(ok),'last_train':int(p.max()) if len(p) else None}

def sequence_bound_test()->dict:
    ids=np.array([0,1,2,10,11,12,20])
    chunks=contiguous_chunks(ids)
    ok=[list(x) for x in chunks]==[[0,1,2],[10,11,12],[20]]
    return {'gate':'SEQUENCE_BOUND','passed':bool(ok)}

def chronology_test()->dict:
    folds=expanding_folds(600,3,12,min_train_rows=100,min_validation_rows=50)
    ok=all(int(tr.max()) < int(va.min()) and int(va.min())-int(tr.max())>12 for tr,va in folds)
    return {'gate':'CHRONOLOGY','passed':bool(ok)}

def run_core_ci()->dict:
    # Causal feature example. A deliberate leaky feature is verified separately by selftest.
    def causal(df): return df['x'].rolling(8,min_periods=1).mean().to_numpy()
    gates=[future_perturbation_test(causal),label_overlap_test(),sequence_bound_test(),chronology_test()]
    return {'schema':'CP_LEAKAGE_ADVERSARIAL_CI_V1','passed':all(x['passed'] for x in gates),'gates':gates}

from __future__ import annotations
import json
import numpy as np
import pandas as pd
from pathlib import Path
from models.models import CandidateSpec
from models.model_lab import apply_fold_training_memory, expanding_folds

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def main():
    # Three years of H1-like chronology. Only signal_time is needed for the helper.
    n=24*365*3
    df=pd.DataFrame({'signal_time':pd.date_range('2020-01-01',periods=n,freq='h')})
    folds=expanding_folds(df,CFG)
    spec=CandidateSpec('xgboost','mem6',{'training_memory_months':6})
    original_validation=[va.copy() for _,va in folds]
    applied=[]
    for (tr,va),orig_va in zip(folds,original_validation):
        fit_tr,meta=apply_fold_training_memory(df,tr,spec,CFG)
        assert np.array_equal(va,orig_va), 'validation indices changed by training memory'
        assert len(fit_tr)<=len(tr)
        applied.append(meta)
    assert any(x.get('applied') for x in applied), applied
    src=(ROOT/'models/model_lab.py').read_text(encoding='utf-8')
    segment=src[src.index('def candidate_cv'):src.index('def acceptance(')]
    assert 'df, memory_info = apply_candidate_memory(df, spec, cfg)' not in segment
    assert 'validation_window_preserved' in segment
    print('TRAINING_MEMORY_CV_INVARIANT_SELFTEST PASS')

if __name__=='__main__': main()

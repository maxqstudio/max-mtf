import numpy as np
from data.leakage_adversarial_ci import *
def req(c,m):
    if not c: raise AssertionError(m)
r=run_core_ci(); req(r['passed'],'core leakage CI must pass legal causal pipeline')
def leaky(df): return (df['x'].shift(-1).fillna(df['x']).to_numpy())
x=future_perturbation_test(leaky); req(not x['passed'],'future perturbation must detect deliberate future leak')
req(label_overlap_test()['passed'],'label overlap purge failed')
req(sequence_bound_test()['passed'],'sequence discontinuity failed')
print('LEAKAGE_ADVERSARIAL_SELFTEST PASS')

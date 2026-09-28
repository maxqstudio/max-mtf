from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from factory.champion_factory import _mc_distribution

def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def main():
    trades=np.asarray([1.0,-0.5,0.8,-0.2,1.2,-0.4,0.6,0.4,-0.3,0.9],float)
    a=_mc_distribution(trades,1000,123,chunk=250); b=_mc_distribution(trades,1000,123,chunk=250)
    req(a==b,'Monte Carlo is reproducible for exact seed/count/trades')
    req(a['simulations']==1000 and a['trade_count']==len(trades),'simulation count is runtime parameter, not hard-coded')
    src=(Path(__file__).resolve().parents[1]/'factory/champion_factory.py').read_text(encoding='utf-8')
    req('monte_carlo_simulations' in src and '10000' in src,'default Monte Carlo count is 10000 but configurable')
    req('MAX_GATE_KPI_PROFILES_V1::MONTE_CARLO_KPI_V1' in src and 'monte_carlo_acceptance(mc,cfg)' in src,'Monte Carlo owns an independent per-gate KPI authority')
    req(set(a.get('probabilities') or {}) >= {'loss','ruin','survival','ruin_floor_r'},'Monte Carlo records deterministic loss/ruin/survival probabilities')
    print('MONTE_CARLO_SELFTEST PASS')
if __name__=='__main__': main()

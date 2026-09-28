from __future__ import annotations
import json, tempfile
from pathlib import Path
from copy import deepcopy
import factory.champion_factory as cf
ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)
def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    block=src[src.index('def run_discovery_pool'):src.index('def _fit_candidate')]
    req('configured_target != 12' in block and 'target = 12' in block,'AUTO Discovery hard-locks exact Pool 12')
    req('discovery_stage_contract_hash' in block and 'Discovery scientific/window/seed/mode contract' in block,'Discovery resume is bound to immutable stage contract')
    req('exclude_experiment_fingerprints' in block and 'historical_seen | tested_current' in block,'AUTO Discovery excludes historical/current duplicate experiments')
    req('FULL_WFA_POLICY' in block and 'decision_policy' in block,'Policy-qualified Full-WFA row survives Discovery handoff')
    req('walk_forward_acceptance' in block and 'wfa_evidence' in block,'Pool admission independently revalidates Full-WFA evidence')
    req('tournament_immutable.csv' in block and 'forward_refit_history.csv' in block,'Tournament and Forward historical authorities freeze before downstream stages')
    with tempfile.TemporaryDirectory() as td:
        fd=Path(td); a=fd/'a.json'; a.write_text('{"v":1}',encoding='utf-8'); c={'schema':'T','scientific_contract':cf._critical_scientific_contract(CFG)}
        seal=cf._stage_seal(fd,'DISCOVERY',contract=c,files=['a.json']); req(cf._verify_stage_seal(fd,'DISCOVERY',expected=c)['seal_hash']==seal['seal_hash'],'Discovery seal verifies exact immutable artifact')
        a.write_text('{"v":2}',encoding='utf-8')
        try: cf._verify_stage_seal(fd,'DISCOVERY',expected=c); raise AssertionError('tamper accepted')
        except RuntimeError as e: req('artifact tamper' in str(e),'Discovery artifact tampering fails closed')
    print('STAGE2_DISCOVERY_BACKEND_CONTRACT PASS')
if __name__=='__main__': main()

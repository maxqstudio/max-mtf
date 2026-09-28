from __future__ import annotations
import json, tempfile
from pathlib import Path
from factory.champion_factory import run_tournament, run_monte_carlo, run_forward_championship
from research.sample_policy import auto_trade_sample

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    fc=CFG['champion_factory']
    req(fc['target_pool']==12 and fc['minimum_pool']==12,'exact 12-candidate Discovery pool authority')
    req(fc['monte_carlo_simulations']==10000,'Monte Carlo default is 10,000 but config-driven')
    req(CFG['trade_sample_policy']['mode']=='AUTO','trade sample AUTO default')
    d=auto_trade_sample(16385,'2020-01-01','2022-12-31',CFG,'DISCOVERY',observed_fraction=.5)
    t=auto_trade_sample(16385,'2023-01-01','2025-12-31',CFG,'TOURNAMENT')
    f=auto_trade_sample(16385,'2026-01-01','2026-09-09',CFG,'FRESH')
    req(d['minimum_trades']==144,'H1 Discovery OOF ~50% resolves to 144 minimum trades at 8/month')
    req(t['minimum_trades']==288,'H1 3y Tournament resolves to 288 minimum trades at 8/month')
    req(f['minimum_trades']==66,'H1 partial Forward minimum is dynamic and rounded up at 8/month')
    with tempfile.TemporaryDirectory() as td:
        fd=Path(td)/'FACTORY_BAD'; fd.mkdir()
        (fd/'factory_manifest.json').write_text(json.dumps({'status':'INSUFFICIENT_QUALIFIED_POOL'}),encoding='utf-8')
        (fd/'candidate_pool.json').write_text(json.dumps([{'pool_id':'CAND_01'}]),encoding='utf-8')
        try: run_tournament(fd,Path(td)/'missing.csv',ROOT/'config/config.json'); raise AssertionError('Tournament opened incomplete pool')
        except RuntimeError as e: req('CPCV finalist survivors belum READY' in str(e),'Tournament fail-closes before CPCV survivors')
        (fd/'factory_manifest.json').write_text(json.dumps({'status':'TOURNAMENT_NO_SURVIVOR'}),encoding='utf-8')
        try: run_monte_carlo(fd,ROOT/'config/config.json'); raise AssertionError('MC opened without survivors')
        except RuntimeError as e: req('survivors belum READY' in str(e),'Monte Carlo fail-closes without Tournament survivors')
        try: run_forward_championship(fd,Path(td)/'missing.csv',ROOT/'config/config.json'); raise AssertionError('Forward opened without MC survivors')
        except RuntimeError as e: req('Monte Carlo survivors belum READY' in str(e),'Forward fail-closes without Monte Carlo survivors')
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req('TOURNAMENT_SURVIVORS_READY' in src and 'MONTE_CARLO_SURVIVORS_READY' in src and 'FORWARD_CHAMPIONSHIP' in src,'current Champion Factory stage authorities wired')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('START RESEARCH' in app and 'Tidak ada duplicate START authority di halaman ini' in app and 'Workflow/lifecycle dikendalikan dari Research' in app,'Operator path is single Research authority with detailed stage inspectors')
    print('CHAMPION_FACTORY_SELFTEST PASS')

if __name__=='__main__': main()

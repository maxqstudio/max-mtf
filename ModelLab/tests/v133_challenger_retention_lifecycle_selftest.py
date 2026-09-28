from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from factory.champion_factory import _stage_seal
from factory.challenger_registry import load_challenger_registry, mark_challenger_promoted
from factory.factory_challenger_bridge import register_factory_winner_as_model_challenger

ROOT=Path(__file__).resolve().parents[1]


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def writej(path:Path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2),encoding='utf-8')


def make_factory(root:Path, stamp:str, family:str='xgboost')->Path:
    fd=root/f'FACTORY_{stamp}_UTC_AUTO001_ABCD'
    rt=fd/'champion_runtime'; rt.mkdir(parents=True)
    onnx=rt/'champion.onnx'; onnx.write_bytes((f'onnx-{stamp}-{family}').encode())
    runtime={
        'schema':'CP_CHAMPION_RUNTIME_V2','family':family,
        'artifacts':{'onnx':'champion.onnx','onnx_sha256':sha(onnx)},
        'parity':{'max_abs_error':0.0},
    }
    writej(rt/'runtime_manifest.json',runtime)
    pool=f'POOL-{stamp}'
    champion={
        'pool_id':pool,'family':family,'name':f'{family}-{stamp}','params':{'depth':4},
        'take_threshold':0.61,'decision_policy':None,'selected_utc':f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}+00:00',
        'runtime_manifest':'champion_runtime/runtime_manifest.json','onnx_parity':{'max_abs_error':0.0},
        'metrics':{'trades':100,'profit_factor':1.6,'expectancy_r':0.55,'max_drawdown_r':5.0,'recovery_factor':3.2,'win_rate':0.52,'payoff_ratio':1.4,'cvar95_r':-1.0},
    }
    writej(fd/'champion.json',champion)
    seal=_stage_seal(fd,'CHAMPION',contract={'test':'v1.3.3'},files=['champion.json','champion_runtime/runtime_manifest.json','champion_runtime/champion.onnx'])
    writej(fd/'factory_manifest.json',{
        'status':'FACTORY_WINNER','champion':pool,'champion_terminal_seal_hash':seal['seal_hash'],'next_required':'REGISTER_MODEL_CHALLENGER'
    })
    return fd


def main():
    graph=(ROOT/'max_graph'/'factory_graph.py').read_text(encoding='utf-8')
    worker=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')

    req('REGISTER_MODEL_CHALLENGER' in graph and 'register_model_challenger' in graph,'LangGraph must have explicit Model Challenger registration stage/node')
    req('register_factory_winner_as_model_challenger' in graph,'LangGraph winner path must call Factory->Model Challenger bridge')
    req('MODEL_CHALLENGER_REGISTRATION_FAILED' in graph,'Model Challenger registration failure must fail closed')
    req('promote(' not in graph and 'promote_strategy_challenger' not in graph,'LangGraph Factory must not own Model/Strategy promotion')
    req('register_optimizer_challenger' in worker,'Strategy Optimizer winner must still register Strategy Challenger')
    req('promote_strategy_challenger(APP_DIR' in app,'Strategy promotion remains explicit UI/Owner action')

    with tempfile.TemporaryDirectory() as td:
        td=Path(td); appdir=td/'app'; factories=td/'factories'
        f1=make_factory(factories,'20260918_010101')
        f2=make_factory(factories,'20260918_020202')
        f3=make_factory(factories,'20260918_030303')

        r1=register_factory_winner_as_model_challenger(f1,appdir)
        r2=register_factory_winner_as_model_challenger(f2,appdir)
        reg=load_challenger_registry(appdir)
        req(len(reg['entries'])==2,'Two eligible Factory winners must coexist as two retained Model Challengers')
        ids=[x['challenger_id'] for x in reg['entries']]
        req(len(set(ids))==2,'Factory winners require unique persistent Challenger IDs')
        req(all(x['status']=='CHALLENGER' for x in reg['entries']),'New Challenger registration must not auto-promote')

        # Replay/resume must be idempotent.
        register_factory_winner_as_model_challenger(f1,appdir)
        reg=load_challenger_registry(appdir)
        req(len(reg['entries'])==2,'Replay of the same Factory winner must not duplicate registry entry')

        # Simulate explicit Owner promotion of challenger 2. Later Factory winners may
        # not demote/replace it and may not delete the older unpromoted challenger.
        id2=r2['evidence']['challenger_id']
        mark_challenger_promoted(appdir,id2,'MODEL-CHAMPION-OWNER-001')
        r3=register_factory_winner_as_model_challenger(f3,appdir)
        reg=load_challenger_registry(appdir)
        req(len(reg['entries'])==3,'Third Factory winner must append, not replace old Challengers')
        byid={x['challenger_id']:x for x in reg['entries']}
        req(byid[id2]['status']=='PROMOTED','Previously Owner-promoted Challenger status must survive later registrations')
        req(byid[r1['evidence']['challenger_id']]['status']=='CHALLENGER','Older unpromoted Challenger must remain held')
        req(byid[r3['evidence']['challenger_id']]['status']=='CHALLENGER','New Factory winner must remain Challenger until Owner promotes')
        req(r3['evidence']['promotion_performed'] is False,'Factory bridge must explicitly record no promotion performed')

    print('V1.3.3 CHALLENGER RETENTION LIFECYCLE SELFTEST PASS')

if __name__=='__main__':
    main()

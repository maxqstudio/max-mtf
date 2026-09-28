from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

import scientist.chat.scientist_chat as sc
import scientist.chat.scientist_chat_jobs as jobs
from host.provider_catalog import ProviderRequestError

ROOT=Path(__file__).resolve().parents[1]
COUNT=0

def req(cond,msg):
    global COUNT
    if not cond:
        raise AssertionError(msg)
    COUNT+=1


def buffered_cfg(*, fallback=True):
    cfg={
        "provider":"primary","base_url":"https://primary.test/v1/","api_key_env":"PRIMARY_CHAT_KEY","model":"m1",
        "stack":[{"provider":"primary","base_url":"https://primary.test/v1/","api_key_env":"PRIMARY_CHAT_KEY","model":"m1","enabled":True}],
        "chat_model_profiles":{
            "m1":{"streaming":False,"timeout_sec":11,"max_output_tokens":512},
            "m2":{"streaming":False,"timeout_sec":22,"max_output_tokens":1024},
        },
    }
    if fallback:
        cfg["chat_fallback_stack"]=[{"provider":"secondary","base_url":"https://secondary.test/custom/v1/","api_key_env":"SECONDARY_CHAT_KEY","model":"m2","enabled":True}]
    return cfg


def make_job(app: Path, jid: str, *, status="RUNNING", created=None, pid=None):
    pp=jobs.paths_for(app,jid)
    obj={
        "schema":"MAX_SCIENTIST_CHAT_JOB_V3_CAS","job_id":jid,"status":status,
        "created_utc":created or jobs.utcnow(),"updated_utc":jobs.utcnow(),"pid":pid,
        "factory_id":"F","request_id":"R","thread_id":"T","hard_timeout_sec":30,
        "phase":status,"result":None,"error":None,
    }
    jobs._atomic_write_json(pp["job"],obj)
    return obj


def write_stage(fd: Path, manifest: dict, stage: str, key: str, artifact: str, payload):
    (fd/artifact).write_text(json.dumps(payload,sort_keys=True),encoding="utf-8")
    contract={"schema":f"TEST_{stage}_CONTRACT","nonce":stage}
    seal={
        "schema":"MAX_STAGE_SEAL_V1","stage":stage,
        "contract":contract,"contract_hash":sc._stable_hash(contract),
        "artifacts":{artifact:sc._sha_file(fd/artifact)},
    }
    seal["seal_hash"]=sc._stable_hash(seal)
    seal_name=f"{stage.lower()}_terminal_seal.json"
    (fd/seal_name).write_text(json.dumps(seal,sort_keys=True),encoding="utf-8")
    manifest[key]={
        "stage_contract":contract,"stage_contract_hash":sc._stable_hash(contract),
        "terminal_seal_file":seal_name,"terminal_seal_hash":seal["seal_hash"],
    }


def test_store_atomicity():
    with tempfile.TemporaryDirectory() as td:
        store=sc.ScientistChatStore(Path(td)/"chat"); fid="FACTORY"
        old=store.current_thread_id(fid)
        store.save(fid,[{"role":"user","content":"old"}],thread_id=old)
        # Repeated simultaneous stale-save vs clear: regardless of interleaving,
        # the stale turn must not exist after both operations settle.
        for _ in range(24):
            current=store.current_thread_id(fid)
            barrier=threading.Barrier(2); errs=[]
            def stale():
                try:
                    barrier.wait(); store.save(fid,[{"role":"assistant","content":"STALE"}],thread_id=current)
                except Exception as exc: errs.append(exc)
            def clear():
                barrier.wait(); store.clear(fid)
            a=threading.Thread(target=stale); b=threading.Thread(target=clear); a.start(); b.start(); a.join(); b.join()
            assert all(m.get("content")!="STALE" for m in store.load(fid))
            assert store.current_thread_id(fid)!=current
        req(True,"clear vs stale save race resurrected history")
        path=store.path_for(fid); path.write_text('{"broken":',encoding="utf-8")
        try: store.load(fid); raise AssertionError("corrupt chat JSON was hidden")
        except RuntimeError as exc: assert "SCIENTIST_CHAT_STORE_CORRUPT" in str(exc)
        req(True,"corrupt chat JSON did not fail closed")


def test_job_cas_and_idempotency():
    with tempfile.TemporaryDirectory() as td:
        app=Path(td); (app/'scientist/chat/scientist_chat_worker.py').write_text('pass',encoding='utf-8')
        calls=[]; old_popen=jobs.subprocess.Popen
        class FakePopen:
            def __init__(self,*a,**k):
                calls.append(1); time.sleep(.03); self.pid=987654
        jobs.subprocess.Popen=FakePopen
        try:
            request={"factory_id":"F","thread_id":"T","request_id":"REQ_SAME","selected_model":"m1","llm_cfg":{"timeout_sec":30}}
            out=[]; barrier=threading.Barrier(2)
            def run(): barrier.wait(); out.append(jobs.start_job(app,request,"secret"))
            t1=threading.Thread(target=run); t2=threading.Thread(target=run); t1.start(); t2.start(); t1.join(); t2.join()
            req(len(out)==2 and out[0]["job_id"]==out[1]["job_id"] and len(calls)==1,"duplicate request_id created duplicate workers")
        finally:
            jobs.subprocess.Popen=old_popen

        jid="CHAT_RACE"; make_job(app,jid)
        barrier=threading.Barrier(2); results=[]
        def complete():
            barrier.wait(); results.append(jobs.commit_terminal_job(app,jid,"COMPLETED",{"result":{"content":"ok"},"completed_utc":jobs.utcnow()}))
        def cancel():
            barrier.wait(); results.append(jobs.cancel_job(app,jid))
        a=threading.Thread(target=complete); b=threading.Thread(target=cancel); a.start(); b.start(); a.join(); b.join()
        final=jobs._read_json(jobs.paths_for(app,jid)["job"],{})
        assert final["status"] in jobs.TERMINAL_STATUSES
        before=json.dumps(final,sort_keys=True)
        jobs.update_active_job(app,jid,{"status":"RUNNING","partial_text":"late"})
        assert json.dumps(jobs._read_json(jobs.paths_for(app,jid)["job"],{}),sort_keys=True)==before
        req(True,"STOP/COMPLETED terminal race is not monotonic")

        jid2="CHAT_COMPLETED"; make_job(app,jid2)
        jobs.commit_terminal_job(app,jid2,"COMPLETED",{"completed_utc":jobs.utcnow()})
        req(jobs.cancel_job(app,jid2)["status"]=="COMPLETED","CANCELLED overwrote COMPLETED")

        old=(time.time()-500)
        from datetime import datetime, timezone
        jid3="CHAT_TIMEOUT"; make_job(app,jid3,created=datetime.fromtimestamp(old,timezone.utc).isoformat(),pid=None)
        final=jobs.load_job(app,jid3)
        assert final["status"]=="FAILED" and final["error"]=="CHAT_HARD_TIMEOUT"
        assert jobs.cancel_job(app,jid3)["status"]=="FAILED"
        req(True,"hard timeout did not preserve one immutable terminal transition")


def test_provider_exactly_once_and_routes():
    old_chat,old_stream=sc.chat_completion,sc.stream_chat_completion
    try:
        cfg=buffered_cfg(); calls=[]
        def internal_typeerror(base,model,key,messages,**kwargs):
            calls.append(model); raise TypeError("internal provider implementation bug")
        sc.chat_completion=internal_typeerror
        try: sc.discuss(cfg,selected_model="m1",api_key="p",history=[],user_prompt="x",context={"sources":[]},allow_fallback=False)
        except RuntimeError: pass
        req(calls==["m1"],"internal TypeError triggered duplicate provider invocation")

        calls=[]
        def auth(base,model,key,messages,**kwargs): calls.append(model); raise ProviderRequestError("HTTP 401 auth",status_code=401)
        sc.chat_completion=auth
        try: sc.discuss(cfg,selected_model="m1",api_key="p",history=[],user_prompt="x",context={"sources":[]},allow_fallback=True)
        except RuntimeError: pass
        req(calls==["m1"],"auth failure triggered a second request")

        calls=[]
        def timeout(base,model,key,messages,**kwargs): calls.append(model); raise ProviderRequestError("HTTP 504 timeout",status_code=504)
        sc.chat_completion=timeout
        try: sc.discuss(cfg,selected_model="m1",api_key="p",history=[],user_prompt="x",context={"sources":[]},allow_fallback=True)
        except RuntimeError: pass
        req(calls==["m1"],"timeout triggered unsafe duplicate/fallback request")

        cfgs=buffered_cfg(fallback=False); cfgs["chat_model_profiles"]={"m1":{"streaming":True,"stream_fallback_to_buffered":True}}
        calls=[]
        def stream_unsupported(base,model,key,messages,**kwargs): calls.append("stream"); raise ProviderRequestError("no SSE",category="STREAM_UNSUPPORTED")
        def buffered_ok(base,model,key,messages,**kwargs): calls.append("buffered"); return {"choices":[{"message":{"content":"ok"}}]}
        sc.stream_chat_completion=stream_unsupported; sc.chat_completion=buffered_ok
        out=sc.discuss(cfgs,selected_model="m1",api_key="p",history=[],user_prompt="x",context={"sources":[]})
        req(calls==["stream","buffered"] and out["content"]=="ok","allowed stream capability fallback was not exactly once")

        cfg=buffered_cfg(); os.environ["SECONDARY_CHAT_KEY"]="secondary-secret"; calls=[]
        def route_call(base,model,key,messages,**kwargs):
            calls.append((base,model,key,dict(kwargs)))
            if model=="m1": raise ProviderRequestError("429 quota",status_code=429)
            return {"choices":[{"message":{"content":"fallback ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}
        sc.chat_completion=route_call
        out=sc.discuss(cfg,selected_model="m1",api_key=("fixture-"+"primary"),history=[],user_prompt="x",context={"sources":[]},allow_fallback=True)
        fb=calls[1]
        req(fb[0]=="https://secondary.test/custom/v1/" and fb[1]=="m2" and fb[2]=="secondary-secret" and out["answering_route"]["provider"]=="secondary" and out["answering_route"]["api_key_env"]=="SECONDARY_CHAT_KEY","explicit fallback route identity was collapsed/lost")
        req(fb[3].get("timeout")==22 and fb[3].get("max_tokens")==1024 and out["chat_profile"]["max_output_tokens"]==1024,"fallback answering model did not receive its own request budget")

        # Legacy local adapter compatibility is decided before the call; one call succeeds.
        calls=[]
        def legacy(base,model,key,messages,temperature=0.2,timeout=60): calls.append(model); return {"choices":[{"message":{"content":"legacy ok"}}]}
        sc.chat_completion=legacy
        out=sc.discuss(buffered_cfg(fallback=False),selected_model="m1",api_key="p",history=[],user_prompt="x",context={"sources":[]})
        req(calls==["m1"] and out["content"]=="legacy ok","pre-call legacy signature adaptation failed")
    finally:
        sc.chat_completion=old_chat; sc.stream_chat_completion=old_stream
        os.environ.pop("SECONDARY_CHAT_KEY",None)


def test_sealed_context_and_readonly():
    with tempfile.TemporaryDirectory() as td:
        fd=Path(td)/"FACTORY"; fd.mkdir()
        manifest={"status":"MONTE_CARLO_SURVIVORS_READY","stage":"MONTE_CARLO","research_contract_hash":"x"}
        write_stage(fd,manifest,"CPCV","cpcv","cpcv_qualification_evidence.json",{"candidates_evaluated":1,"survivor_count":1,"rows":[{"pool_id":"P1"}]})
        write_stage(fd,manifest,"TOURNAMENT","tournament","tournament_leaderboard.json",[{"pool_id":"P1","status":"PASS"}])
        write_stage(fd,manifest,"MONTE_CARLO","monte_carlo","monte_carlo_evidence.json",{"simulation_count":1000,"rows":[{"pool_id":"P1"}]})
        (fd/'factory_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        (fd/'forward_evidence_001.json').write_text(json.dumps({"LOCKED_SECRET":"NO"}),encoding='utf-8')
        (fd/'raw_training.csv').write_text('RAW_SECRET\nNO\n',encoding='utf-8')
        ctx=sc.build_read_only_context(fd,scope="MODEL & CANDIDATES")
        req(all(ctx["authority"].get(k) is False for k in ("can_execute","can_modify_research","can_modify_settings","can_promote")) and ctx["authority"]["tools"]==[],"Scientist Chat read-only authority drifted")
        blob=json.dumps(ctx)
        req("LOCKED_SECRET" not in blob and "RAW_SECRET" not in blob and ctx["authority"]["locked_or_fresh_forward_evidence_exposed"] is False,"raw/Fresh/locked evidence leaked into Chat")

        originals={name:(fd/name).read_bytes() for name in ("cpcv_qualification_evidence.json","tournament_leaderboard.json","monte_carlo_evidence.json")}
        for artifact,label in (("cpcv_qualification_evidence.json","CPCV"),("tournament_leaderboard.json","TOURNAMENT"),("monte_carlo_evidence.json","MONTE_CARLO")):
            (fd/artifact).write_text('{"tampered":true}',encoding='utf-8')
            try: sc.build_read_only_context(fd,scope="MODEL & CANDIDATES"); raise AssertionError(f"tampered {label} accepted")
            except RuntimeError as exc: assert "ARTIFACT_TAMPER" in str(exc)
            (fd/artifact).write_bytes(originals[artifact])
            req(True,f"tampered {label} evidence was not rejected")


def test_prefactory_live_hardware_truth():
    # Before START RESEARCH there is no frozen Factory hardware file yet. Scientist
    # must still receive current-host truth and must not infer accelerators from
    # settings that merely allow them.
    hw={
        "schema":"CP_HARDWARE_PROFILE_V1","captured_utc":"2026-09-14T00:00:00Z","profile_hash":"HW",
        "os":{"system":"Windows","release":"11"},
        "cpu":{"name":"AMD Ryzen Test","physical_cores":6,"logical_threads":12,"planning_cores":6,"core_count_source":"PSUTIL","architecture":"AMD64"},
        "memory":{"total_gib":32.0,"available_gib":21.0,"source":"PSUTIL"},
        "nvidia":{"detected":False,"devices":[]},
        "torch":{"installed":True,"torch_version":"2.x+cpu","cuda_available":False,"cuda_version":None},
    }
    plan={
        "schema":"CP_COMPUTE_BACKEND_V1","mode":"AUTO","fallback_cpu":True,
        "temporal_dl":{"backend":"CPU","torch_device":"cpu"},"xgboost":{"backend":"CPU"},"lightgbm":{"backend":"CPU"},"random_forest":{"backend":"CPU"},
        "vulkan":{"state":"UNAVAILABLE","training_backend":False},"notes":[],
        "capabilities":{"torch":{"accelerator":None,"torch_device":"cpu"},"xgboost_cuda":{"usable":False},"lightgbm_gpu":{"usable":False},"opencl":{"device_evidence":False},"vulkan":{"detected":False},"cpu":{"usable":True}},
    }
    settings=sc.build_research_settings_snapshot({"compute":{"mode":"AUTO","allow_cuda":True,"allow_rocm":True,"allow_vulkan":True,"allow_opencl":True}})
    ctx=sc.build_read_only_context(None,scope="AUTO",research_settings=settings,live_hardware=hw,live_compute_plan=plan)
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    prompt=sc._chat_system_prompt()
    req(
        ctx["factory"]["status"]=="NO_FACTORY_CONTEXT"
        and ctx["live_hardware"]["cpu"]["name"]=="AMD Ryzen Test"
        and ctx["live_hardware"]["nvidia"]["detected"] is False
        and ctx["live_compute_plan"]["temporal_dl"]["backend"]=="CPU"
        and any(x.get("id")=="LIVE_HW" for x in ctx["sources"])
        and any(x.get("id")=="LIVE_COMPUTE" for x in ctx["sources"])
        and "do not ask the Owner to repeat hardware specs" in prompt
        and "live_hardware=_chat_live_hw" in app
        and "live_compute_plan=_chat_live_compute" in app,
        "pre-Factory Scientist context does not carry current-host hardware/compute truth",
    )


def test_persistence_visibility_and_ui_identity():
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    completed=app[app.index('if status=="COMPLETED"'):app.index('elif status=="CANCELLED"')]
    req(all(token in completed for token in ('"provider":ans.get("provider")','"cost":ans.get("cost")','"answering_route":ans.get("answering_route")')),"successful assistant provenance provider/cost/route is not persisted")

    old=sc.chat_completion
    try:
        captured={}
        def fake(base,model,key,messages,**kwargs): captured["messages"]=messages; return {"choices":[{"message":{"content":"ok"}}]}
        sc.chat_completion=fake
        hist=[{"role":"user","content":"visible"},{"role":"assistant","content":"INTERNAL_SECRET","error":True,"visibility":"internal"},{"role":"assistant","content":"visible answer"}]
        sc.discuss(buffered_cfg(fallback=False),selected_model="m1",api_key="p",history=hist,user_prompt="next",context={"sources":[]})
        req("INTERNAL_SECRET" not in json.dumps(captured["messages"]),"hidden failed assistant text leaked into later prompt history")
    finally: sc.chat_completion=old

    # Fallback default must remain OFF when caller does not explicitly opt in.
    old=sc.chat_completion; calls=[]
    try:
        def quota(base,model,key,messages,**kwargs): calls.append(model); raise ProviderRequestError("429 quota",status_code=429)
        sc.chat_completion=quota
        try: sc.discuss(buffered_cfg(),selected_model="m1",api_key="p",history=[],user_prompt="x",context={"sources":[]})
        except RuntimeError: pass
        req(calls==["m1"],"Chat fallback default is not OFF")
    finally: sc.chat_completion=old

    comp=(ROOT/'scientist/chat/scientist_chat_component.py').read_text(encoding='utf-8')
    req(all(x in comp for x in ('setTriggerValue("send",','setTriggerValue("stop",','setStateValue("reconcile",','thread_id:threadId')) and 'event_thread==thread_id' in app,"thread identity/liveness is not carried through SEND/STOP/reconcile")
    req('root._scientistResetTimer' in comp and 'setStateValue("reconcile"' in comp and 'root.dataset.resetting="0"' in comp and 'root.dataset.resetting==="1"' in comp and '_scientist_chat_clear_requested' in app and 'on_clear_change=_request_scientist_clear' in app and 'on_poll_change=' not in comp,"Clear reset must rotate server thread and reconcile through stable component state")

    req('"reconcile": ""' in comp and 'on_reconcile_change=lambda: None' in comp and '_scientistReconcileInterval' in comp and 'setInterval(' in comp and 'setTriggerValue("poll"' not in comp, "recurring hidden reconcile heartbeat missing or legacy poll trigger returned")


def main():
    test_store_atomicity()
    test_job_cas_and_idempotency()
    test_provider_exactly_once_and_routes()
    test_sealed_context_and_readonly()
    test_prefactory_live_hardware_truth()
    test_persistence_visibility_and_ui_identity()
    assert COUNT==25,COUNT
    print(f"STAGE10_SCIENTIST_CHAT_BACKEND_CONTRACT PASS {COUNT}/25")

if __name__=='__main__':
    main()

from pathlib import Path
import json
import tempfile

ROOT=Path(__file__).resolve().parents[1]
app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
worker=(ROOT/'factory/factory_worker.py').read_text(encoding='utf-8')

def req(cond,msg):
    if not cond:
        raise AssertionError(msg)

# UI start path must not own blocking audit/repair.
start_block=app.split('def _start_auto_background',1)[1].split('\ndef ',1)[0]
req('audit_dataset(' not in start_block,'START UI still performs blocking data audit')
req('run_data_quality_preflight' in start_block,'AUTO payload must request worker-side DQ preflight')
req('start_factory_job' in start_block,'START must spawn owned factory worker')

# v0.11.1 staged authority: local/cached audit first, MT5 repair only after FAIL.
req('def _prepare_auto_data_quality' in worker,'worker preflight helper missing')
helper_src=worker.split('def _prepare_auto_data_quality',1)[1].split('\ndef main',1)[0]
req('audit_dataset(payload["dataset"],broker_reconcile=False,use_cached_broker_proof=True)' in helper_src,'initial worker audit must be local/cached and never launch MT5')
req('run_gap_repair_cycle' in helper_src,'repair stage missing')
req(helper_src.index('broker_reconcile=False') < helper_src.index('run_gap_repair_cycle'),'MT5 repair may run before local audit failure')
req('research_readiness(report)' in helper_src,'research readiness gate missing')
req('DATA QUALITY GATE BLOCKED' in helper_src,'non-repairable fail-closed path missing')
req('llm_data_quality_context(report)' in helper_src,'DQ context must be frozen into runtime config')
req('atomic_write_json(cfg_path,raw)' in helper_src,'runtime config DQ freeze must be atomic')

# Operator-visible lifecycle must distinguish Data Quality from actual research.
req('DATA_QUALITY_PREFLIGHT' in worker,'worker lifecycle has no explicit Data Quality preflight state')
req('mark_research_running()' in worker,'worker never transitions from DQ preflight to research RUNNING')
req(worker.index('initial_status="DATA_QUALITY_PREFLIGHT"') < worker.index('run_auto_factory('),'AUTO lifecycle can expose RUNNING before DQ authority')
req('DATA_QUALITY_PREFLIGHT' in app and 'Data Quality preflight' in app,'UI does not expose Data Quality preflight state')

auto=worker.split('if action=="AUTO":',1)[1].split('elif action=="DISCOVERY"',1)[0]
req('_prepare_auto_data_quality' in auto,'AUTO worker does not execute DQ preflight')
req(auto.index('_prepare_auto_data_quality') < auto.index('run_auto_factory'),'DQ preflight must happen before research engine')
req('latest_failed' in app and 'cp-lifecycle-error' in app,'worker preflight failure is not surfaced in lifecycle footer')

# Execute deterministic fixtures. PASS must not touch MT5 repair. Repairable FAIL must.
import factory.factory_worker as fw
orig={k:getattr(fw,k) for k in ('audit_dataset','research_readiness','llm_data_quality_context','load_job','save_job','discover_mt5_gap_fill_targets','run_gap_repair_cycle')}
try:
    saved=[]; repair_calls=[]
    pass_report={'status':'VALID_WITH_WARNINGS','sha256':'abc123','warnings':['W1'],'hard_reasons':[],'broker_reconciliation':{'verified':True,'source_backed_missing_count':0,'dataset_only_count':0}}
    fw.audit_dataset=lambda path,**kwargs: pass_report
    fw.research_readiness=lambda r:(True,[])
    fw.llm_data_quality_context=lambda r:{'quality_status':r['status']}
    fw.load_job=lambda root,jid:{'job_id':jid,'status':'RUNNING'}
    fw.save_job=lambda root,job:(saved.append(dict(job)) or job)
    fw.discover_mt5_gap_fill_targets=lambda: [{'terminal_exe':'X:/terminal64.exe'}]
    fw.run_gap_repair_cycle=lambda *a,**k:(repair_calls.append((a,k)) or {'report':pass_report})
    with tempfile.TemporaryDirectory() as td:
        cfg=Path(td)/'runtime.json'; cfg.write_text(json.dumps({'agent':{}}),encoding='utf-8')
        events=[]
        got=fw._prepare_auto_data_quality(Path(td),'JOB_X',{'dataset':'dummy.csv'},cfg,events.append,lambda:None)
        frozen=json.loads(cfg.read_text(encoding='utf-8'))
        req(got['status']=='VALID_WITH_WARNINGS','fixture report not returned')
        req(not repair_calls,'PASS path must not open MT5 repair')
        req(frozen['agent']['data_quality_source_sha256']=='abc123','DQ source sha not frozen')
        req(events[0]['stage']=='data_quality_preflight' and events[-1]['current']==5,'preflight progress sequence incomplete')

    # Cache/proof miss is repairable: only now may MT5 stage run.
    local_fail={'status':'VALID_WITH_WARNINGS','sha256':'def456','warnings':['BROKER_RECONCILIATION_NOT_VERIFIED'],'hard_reasons':[],'broker_reconciliation':{'verified':False,'reason':'BROKER_PROOF_CACHE_MISS'}}
    repaired={'status':'VALID','sha256':'ghi789','warnings':[],'hard_reasons':[],'broker_reconciliation':{'verified':True,'source_backed_missing_count':0,'dataset_only_count':0}}
    calls={'audit':0,'repair':0}
    fw.audit_dataset=lambda path,**kwargs:(calls.__setitem__('audit',calls['audit']+1) or local_fail)
    fw.research_readiness=lambda r: ((True,[]) if r.get('sha256')=='ghi789' else (False,['BROKER_RECONCILIATION_REQUIRED']))
    fw.run_gap_repair_cycle=lambda *a,**k:(calls.__setitem__('repair',calls['repair']+1) or {'report':repaired})
    with tempfile.TemporaryDirectory() as td:
        cfg=Path(td)/'runtime.json'; cfg.write_text(json.dumps({'agent':{}}),encoding='utf-8')
        events=[]
        got=fw._prepare_auto_data_quality(Path(td),'JOB_Y',{'dataset':'dummy.csv'},cfg,events.append,lambda:None)
        req(calls['audit']==1 and calls['repair']==1,'repairable FAIL must audit locally once then enter MT5 repair once')
        req(got['sha256']=='ghi789','post-repair verified report not returned')
        req(any(e.get('stage')=='data_quality_repair' for e in events),'repair stage progress missing')

    # Structural corruption must remain fail-closed without MT5.
    invalid={'status':'INVALID','sha256':'bad','warnings':[],'hard_reasons':['INVALID_OHLC_ROWS:1'],'broker_reconciliation':{'verified':False}}
    fw.audit_dataset=lambda path,**kwargs: invalid
    fw.research_readiness=lambda r:(False,['INVALID_OHLC_ROWS:1','BROKER_RECONCILIATION_REQUIRED'])
    calls['repair']=0
    with tempfile.TemporaryDirectory() as td:
        cfg=Path(td)/'runtime.json'; cfg.write_text(json.dumps({'agent':{}}),encoding='utf-8')
        try:
            fw._prepare_auto_data_quality(Path(td),'JOB_Z',{'dataset':'dummy.csv'},cfg,lambda e:None,lambda:None)
            raise AssertionError('invalid DQ path incorrectly continued')
        except RuntimeError as exc:
            req('DATA QUALITY GATE BLOCKED' in str(exc),'invalid DQ did not fail closed')
            req(calls['repair']==0,'structural corruption must not open MT5 repair')
finally:
    for k,v in orig.items(): setattr(fw,k,v)

print('RESEARCH START ASYNC PREFLIGHT SELFTEST PASS')

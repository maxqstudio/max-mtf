from pathlib import Path
import json, tempfile, shutil, hashlib, sys
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent; sys.path.insert(0,str(ROOT))
import strategy.strategy_optimizer as so
import strategy.strategy_optimizer_worker as sow
import strategy.strategy_geometry as sg
import strategy.strategy_challenger_registry as scr
def req(x,msg):
    if not x: raise AssertionError(msg)

with tempfile.TemporaryDirectory() as td:
    t=Path(td); app=t/'ModelLab'; app.mkdir(); (app/'runtime').mkdir()
    ea=t/'Max_MTF.mq5'; shutil.copy2(PKG/'EA_v2_00/baseline/Max_MTF.mq5',ea)
    archive=t/'archive'; challengers=t/'challengers'; challengers.mkdir()
    data=t/'terminal'; (data/'MQL5/Profiles/Tester').mkdir(parents=True)
    runtime_auth=app/'runtime/strategy_authority.json'

    # Patch all runtime authorities to the sandbox.
    old=(so.EA_SOURCE,scr.EA_SOURCE,scr.ARTIFACT_ROOT,scr.EA_ARCHIVE_DIR,scr.RUNTIME_AUTHORITY,sg.RUNTIME_AUTHORITY,sow.EA_SOURCE,sow.compile_ea)
    try:
        so.EA_SOURCE=ea; scr.EA_SOURCE=ea; sow.EA_SOURCE=ea
        scr.ARTIFACT_ROOT=challengers; scr.EA_ARCHIVE_DIR=archive
        scr.RUNTIME_AUTHORITY=runtime_auth; sg.RUNTIME_AUTHORITY=runtime_auth
        sow.compile_ea=lambda req,job:(job/'Max_MTF.ex5','MaxMTF\\Max_MTF')

        params=so.read_ea_optimizer_defaults(ea)
        # Make challenger distinguishable but legal.
        params['InpEntryThreshold']=round(min(0.60,float(params['InpEntryThreshold'])+0.02),2)
        request={'installation':{'data_dir':str(data),'metaeditor':str(t/'metaeditor64.exe'),'terminal':str(t/'terminal64.exe')},'confirm_symbol':'XAGUSD','search_space':so.DEFAULT_SPACE}
        mq5=challengers/'Max_Challenger_TEST.mq5'
        entry=scr._write_challenger_bundle(req=request,params=params,code='STRAT-TEST',mq5=mq5,kpi={},provenance={'source_job_id':'TEST','source_round':1,'source_pass':1},hard_gates={},role_origin='TEST')
        reg={'schema':scr.SCHEMA,'baseline_strategy':scr._baseline_record(),'current_champion':None,'entries':[entry],'tombstones':[],'promotion_history':[],'updated_utc':None}
        scr._atomic_json(scr.registry_path(app),reg)

        result=scr.promote_strategy_challenger(app,'STRAT-TEST',installation=request['installation'])
        req(result['status']=='PROMOTED','first promotion succeeds')
        req(result['demoted_champion'] is None,'zero-Champion bootstrap must not fabricate former Champion')
        req((result.get('baseline_archive') or {}).get('status')=='ARCHIVED_PRE_FIRST_STRATEGY_CHAMPION','seed baseline archived on first promotion')
        rr=scr.load_strategy_registry(app,ensure=False)
        req((rr.get('current_champion') or {}).get('strategy_id')=='STRAT-TEST','first promoted challenger becomes Strategy Champion #1')
        req(not any(x.get('challenger_id')=='STRAT-TEST' for x in rr.get('entries',[])),'promoted challenger removed from active challenger list')
        req(Path(result['baseline_archive']['ea_file']).is_file(),'baseline archive artifact exists')
        req((data/'MQL5/Profiles/Tester/Max_MTF.set').is_file(),'promotion commits isolated Max_MTF Tester preset')
    finally:
        so.EA_SOURCE,scr.EA_SOURCE,scr.ARTIFACT_ROOT,scr.EA_ARCHIVE_DIR,scr.RUNTIME_AUTHORITY,sg.RUNTIME_AUTHORITY,sow.EA_SOURCE,sow.compile_ea=old
print('V200_FIRST_STRATEGY_PROMOTION PASS')

from pathlib import Path
import tempfile, json
import factory.factory_orchestrator as fo
ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('LLM Research Director / Scientist Report' in app and '_render_llm_research_report' in app,'LLM Research Director/Scientist report restored to main UI')
    req('ScientistChatStore' in app and 'Read-only' in app and 'scientist_chat_discuss' in app and 'scientist_chat_drawer' in app,'Scientist Chat restored only as separate read-only discussion room')
    req('START RESEARCH' in app and '_start_auto_background' in app,'Master Orchestrator primary action exposed through global lifecycle')
    sci=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
    req('def operator_chat(' not in sci and 'def propose(' in sci,'Scientist remains research reporter/planner, not chat operator')

    calls=[]
    orig=(fo.run_discovery_pool,fo.run_cpcv_qualification,fo.run_tournament,fo.run_monte_carlo,fo.run_forward_championship,fo.verify_champion_terminal_authority)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        def disc(dataset,config_path,froot,*args,**kwargs):
            fid=kwargs['factory_id']; fd=Path(froot)/fid; fd.mkdir(parents=True,exist_ok=True)
            calls.append(('D',fid))
            man={'status':'DISCOVERY_POOL_READY','qualified_candidates':12,'target_candidates':12}
            (fd/'factory_manifest.json').write_text(json.dumps(man),encoding='utf-8')
            return {'factory':str(fd),'status':'DISCOVERY_POOL_READY','qualified':12,'target':12,'manifest':man}
        cycle={'n':0}
        def cpcv(fd,*args,**kwargs):
            calls.append(('C',Path(fd).name)); man={'status':'CPCV_SURVIVORS_READY'}; (Path(fd)/'factory_manifest.json').write_text(json.dumps(man),encoding='utf-8'); (Path(fd)/'cpcv_survivors.json').write_text(json.dumps([{'pool_id':'CAND_01'}]),encoding='utf-8'); return {'status':'CPCV_SURVIVORS_READY','manifest':man,'survivors':1}
        def tour(fd,*args,**kwargs):
            calls.append(('T',Path(fd).name)); cycle['n']+=1
            status='TOURNAMENT_NO_SURVIVOR' if cycle['n']==1 else 'TOURNAMENT_SURVIVORS_READY'
            man={'status':status};
            if status=='TOURNAMENT_NO_SURVIVOR': man.update({'research_learning_ready':True,'research_feedback_exhausted':False,'next_required':'START_NEW_DISCOVERY_WITH_TOURNAMENT_LEARNING'})
            (Path(fd)/'factory_manifest.json').write_text(json.dumps(man),encoding='utf-8')
            return {'factory':str(fd),'status':status,'survivors':0 if cycle['n']==1 else 3,'manifest':man}
        def mc(fd,*args,**kwargs):
            calls.append(('M',Path(fd).name)); man={'status':'MONTE_CARLO_SURVIVORS_READY'}; (Path(fd)/'factory_manifest.json').write_text(json.dumps(man),encoding='utf-8'); return {'factory':str(fd),'status':man['status'],'survivors':2,'manifest':man}
        def fw(fd,*args,**kwargs):
            calls.append(('F',Path(fd).name)); man={'status':'FACTORY_WINNER'}; (Path(fd)/'factory_manifest.json').write_text(json.dumps(man),encoding='utf-8'); ch={'pool_id':'POOL_001'}; (Path(fd)/'champion.json').write_text(json.dumps(ch),encoding='utf-8'); return {'factory':str(fd),'status':'FACTORY_WINNER','champion':ch,'manifest':man}
        def verify_champion(fd):
            ch=json.loads((Path(fd)/'champion.json').read_text(encoding='utf-8'))
            return {'champion':ch,'manifest':json.loads((Path(fd)/'factory_manifest.json').read_text(encoding='utf-8')),'seal':{'seal_hash':'FIXTURE'}}
        fo.run_discovery_pool,fo.run_cpcv_qualification,fo.run_tournament,fo.run_monte_carlo,fo.run_forward_championship,fo.verify_champion_terminal_authority=disc,cpcv,tour,mc,fw,verify_champion
        try:
            r=fo.run_auto_factory(root,'d.csv','c.json','2020-01-01','2022-12-31','2023-01-01','2025-12-31','2026-01-01','2026-09-10',orchestrator_id='TEST')
        finally:
            fo.run_discovery_pool,fo.run_cpcv_qualification,fo.run_tournament,fo.run_monte_carlo,fo.run_forward_championship,fo.verify_champion_terminal_authority=orig
        req(r['status']=='FACTORY_WINNER' and r['cycles']==2,'Orchestrator restarts only after committed failure learning and reaches Champion')
        req([x[0] for x in calls]==['D','C','T','D','C','T','M','F'],'Orchestrator stage order and automatic restart are correct')
        state=json.loads((root/'_orchestrators'/'TEST.json').read_text())
        req(state['status']=='FACTORY_WINNER' and state['stage']=='DONE','Orchestrator commits terminal Champion state')
    print('ORCHESTRATOR_REPORT_SELFTEST PASS')

if __name__=='__main__': main()

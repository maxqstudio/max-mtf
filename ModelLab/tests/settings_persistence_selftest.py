from __future__ import annotations
import json, tempfile
from datetime import date
from pathlib import Path
from core.settings_store import UserSettingsStore, is_persistable_ui_key, merge_persisted_ui_state


def main():
    base={'agent':{'llm':{'provider':'gemini','model':''}},'models':{'gru':True},'seed':42}
    with tempfile.TemporaryDirectory() as td:
        store=UserSettingsStore(Path(td))
        cfg=json.loads(json.dumps(base)); cfg['agent']['llm']['model']='model-A'; cfg['seed']=77
        r=store.save(cfg,'',{
            'nav_page_v071':'Advanced',
            'factory_selected':'FACTORY_X',
            'main_research_date_range':(date(2026,1,1),date(2026,8,31)),
            'compute_rescan':True,
            'factory_start_btn':True,
            'new_future_button':True,
            'llm_api_key_input':'SECRET_TEST_VALUE',
            'advanced_llm_enable':True,
            'strategy_opt_mt5_installation':'MT5 Monex',
            'strategy_opt_terminal':r'C:\\MT5\\terminal64.exe',
            'strategy_opt_metaeditor':r'C:\\MT5\\metaeditor64.exe',
            'strategy_opt_data_dir':r'C:\\Users\\owner\\AppData\\Roaming\\MetaQuotes\\Terminal\\ABC',
            'strategy_opt_symbol':'EURUSD.m',
            'strategy_opt_confirm_symbol':'XAUUSD.m',
            'strategy_opt_period':'H4',
            'strategy_opt_from':date(2022,2,1),
            'strategy_opt_to':date(2026,9,9),
            'strategy_opt_tick_model':'Every tick based on real ticks',
            'strategy_opt_kpi_pf':1.25,
            'strategy_opt_kpi_rf':0.5,
            'strategy_opt_kpi_exp':0.10,
            'strategy_opt_kpi_h1_trades':20,
            'strategy_opt_params':['InpSL_ATR','InpTP_ATR'],
            'strategy_opt_rounds':4,
            'strategy_opt_scientist':False,
            'strategy_opt_method':'Slow complete',
            'strategy_opt_start_button':True,
            'strategy_opt_continue_button':True,
        })
        loaded,key,meta,ui=store.load(base)
        assert loaded['seed']==77 and loaded['agent']['llm']['model']=='model-A'
        assert ui['nav_page_v071']=='Advanced' and ui['factory_selected']=='FACTORY_X'
        assert ui['main_research_date_range'][0]==date(2026,1,1)
        assert 'compute_rescan' not in ui and 'factory_start_btn' not in ui and 'new_future_button' not in ui
        assert 'llm_api_key_input' not in ui and 'advanced_llm_enable' not in ui
        assert ui['strategy_opt_mt5_installation']=='MT5 Monex'
        assert ui['strategy_opt_terminal'].endswith('terminal64.exe') and ui['strategy_opt_metaeditor'].endswith('metaeditor64.exe') and 'MetaQuotes' in ui['strategy_opt_data_dir']
        assert ui['strategy_opt_symbol']=='EURUSD.m' and ui['strategy_opt_confirm_symbol']=='XAUUSD.m'
        assert ui['strategy_opt_period']=='H4' and ui['strategy_opt_from']==date(2022,2,1) and ui['strategy_opt_to']==date(2026,9,9)
        assert ui['strategy_opt_tick_model']=='Every tick based on real ticks' and ui['strategy_opt_method']=='Slow complete'
        assert ui['strategy_opt_params']==['InpSL_ATR','InpTP_ATR'] and ui['strategy_opt_rounds']==4 and ui['strategy_opt_scientist'] is False
        assert 'strategy_opt_start_button' not in ui and 'strategy_opt_continue_button' not in ui
        assert is_persistable_ui_key('factory_selected') and is_persistable_ui_key('strategy_opt_symbol') and not is_persistable_ui_key('compute_rescan')

        # v0.8.4 navigation persistence: hidden Streamlit widgets disappear from live
        # session state, but their durable values must survive the next save.
        hidden_live={'nav_page_v071':'Research','left_nav_open':True}
        merged=merge_persisted_ui_state(ui,hidden_live)
        assert merged['nav_page_v071']=='Research'
        assert merged['strategy_opt_symbol']=='EURUSD.m'
        assert merged['strategy_opt_kpi_exp']==0.10 and merged['strategy_opt_rounds']==4
        assert merged['strategy_opt_terminal'].endswith('terminal64.exe')
        # Explicit live values still overwrite the durable shadow (False/empty are real values).
        merged2=merge_persisted_ui_state(merged,{'strategy_opt_scientist':False,'strategy_opt_confirm_symbol':''})
        assert merged2['strategy_opt_scientist'] is False and merged2['strategy_opt_confirm_symbol']==''
        store.save(cfg,'',merged2)
        _,_,_,roundtrip=store.load(base)
        assert roundtrip['strategy_opt_symbol']=='EURUSD.m' and roundtrip['strategy_opt_kpi_exp']==0.10
        assert roundtrip['strategy_opt_confirm_symbol']==''

        app_source=Path('app.py').read_text(encoding='utf-8')
        assert '_persistent_ui_cache' in app_source
        assert '_rehydrate_persisted_ui_state(prefix="strategy_opt_")' in app_source
        assert 'merge_persisted_ui_state' in app_source

        raw=Path(r['settings']).read_text(encoding='utf-8')
        assert 'SECRET_TEST_VALUE' not in raw

        # Backup recovery remains intact.
        cfg2=json.loads(json.dumps(cfg)); cfg2['seed']=88
        store.save(cfg2,'',{'nav_page_v071':'Research'})
        store.settings_path.write_text('{broken',encoding='utf-8')
        recovered,_,m2,ui2=store.load(base)
        assert m2['recovered_from_backup'] is True
        assert recovered['seed']==77

        # Legacy payload can contain buttons + plaintext secret-like UI fields. Load must scrub
        # them and self-heal the primary settings file on disk.
        legacy={'schema':'CPMF_USER_SETTINGS_V1','config':cfg,'ui_state':{
            'compute_rescan':False,
            'factory_start_btn':False,
            'llm_api_key_input':'LEAK_ME_NOT',
            'advanced_llm_enable':True,
            'nav_page_v071':'Data',
            'factory_selected':'FACTORY_OLD',
        }}
        store.settings_path.write_text(json.dumps(legacy),encoding='utf-8')
        _,_,legacy_meta,legacy_ui=store.load(base)
        assert legacy_ui=={'nav_page_v071':'Data','factory_selected':'FACTORY_OLD'}
        healed=store.settings_path.read_text(encoding='utf-8')
        assert 'LEAK_ME_NOT' not in healed and 'compute_rescan' not in healed and 'factory_start_btn' not in healed
        assert legacy_meta.get('ui_state_scrubbed') is True

        source=Path('settings_store.py').read_text(encoding='utf-8')
        assert 'CryptProtectData' in source and 'CryptUnprotectData' in source
        assert '_PERSISTENT_UI_EXACT' in source and '_SENSITIVE_UI_TOKENS' in source
    print('SETTINGS_PERSISTENCE_SELFTEST PASS')

if __name__=='__main__': main()

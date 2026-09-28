from pathlib import Path
app=(Path(__file__).resolve().parents[1]/'ui/app.py').read_text(encoding='utf-8')

def req(cond,msg):
    if not cond:
        raise AssertionError(msg)

# START: pending loader must be emitted before the STARTING button.
start_anchor='dataset=_known_factory_dataset(); pending=bool(st.session_state.get("pending_research_start"))'
start=app.index(start_anchor)
chunk=app[start:start+2600]
req(chunk.index('Launching research worker…') < chunk.index('STARTING…'),
    'START loader must render above STARTING button')

# Active lifecycle: live loader must be emitted before PAUSE / STOP row.
active_anchor='if status in {"QUEUED","DATA_QUALITY_PREFLIGHT","RUNNING","PAUSE_REQUESTED","STOP_REQUESTED"}:'
start=app.index(active_anchor)
chunk=app[start:start+3600]
req(chunk.index('cp-busy-row') < chunk.index('c1,c2=st.columns(2,gap="small")'),
    'active research loader must render above PAUSE/STOP controls')
req('busy_text=f"{stage} · {msg}"' in chunk and 'Data Quality preflight' in chunk,'active loader must surface DQ preflight and live stage/message')
req('overflow:visible!important;min-height:max-content!important;' in app,
    'left lifecycle footer must not clip loader content')
req('.st-key-left_nav_footer .cp-busy-row{width:100%!important;margin:0 0 .44rem!important;}' in app,
    'sidebar lifecycle loader must reserve space above buttons')
print('LIFECYCLE_LOADER_LAYOUT_SELFTEST PASS')

from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')
COMP=(ROOT/'scientist/chat/scientist_chat_component.py').read_text(encoding='utf-8')
CHAT=(ROOT/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8')

def req(c,m):
    if not c: raise AssertionError(m)

header=APP[APP.index('with st.container(key="left_nav_header")'):APP.index('with st.container(key="left_nav_nav")')]
req('st.columns(' not in header,'left header still uses Streamlit columns')
req('.st-key-left_nav_hide{position:absolute!important' in APP,'left header hide control not absolutely anchored')
req('cp-side-mark' not in header and 'white-space:normal!important' in APP and 'text-overflow:clip!important' in APP,'left brand must remove CP icon and wrap without clipping')

for token in ['md-table-wrap','md-table','md-h1','md-quote','md-link','renderTable','isTableDivider']:
    req(token in COMP,f'rich Markdown/table support missing: {token}')
req(' is thinking' in COMP and '@keyframes scientist-thinking' in COMP and 'thinking-dots' in COMP,'thinking animation missing')
req('appendMessage(history,{role:"user",content:text},"optimistic")' in COMP,'optimistic sent message missing')
req('showThinking(history,model.options[model.selectedIndex]?.text||model.value' in COMP,'thinking state not triggered on send')
req('root.dataset.pending' in COMP and 'setTriggerValue("stop"' in COMP,'duplicate-send guard / stop-generation bridge missing')
req('assistant-model-label' in COMP and 'answered_by' in COMP,'assistant replies must show answering model')
req('_sanitize_response_text' in CHAT and 'Never invent a cause' in CHAT,'Scientist grounding/safety boundary missing')
req('Markdown tables' in CHAT,'Scientist prompt does not permit structured AI-chat formatting')
print('PASS scientist_chat_ai_ux_selftest')

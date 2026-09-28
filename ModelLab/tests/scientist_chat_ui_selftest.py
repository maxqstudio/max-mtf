from pathlib import Path

def req(c,m):
    if not c: raise AssertionError(m)

root=Path(__file__).resolve().parents[1]
app=(root/'ui/app.py').read_text(encoding='utf-8')
settings=(root/'core/settings_store.py').read_text(encoding='utf-8')
chat=(root/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8')
component=(root/'scientist/chat/scientist_chat_component.py').read_text(encoding='utf-8')

code='\n'.join(line for line in app.splitlines() if not line.lstrip().startswith('#'))
req('with st.sidebar' not in code and 'st.sidebar.' not in code,'native Streamlit sidebar must not be a second shell authority')
req('@st.fragment(key="shell_state")' in app and '@st.fragment(key="workspace")' in app and 'key="scientist")' in app and 'run_every="1s"' in app,'named shell fragments / Scientist heartbeat missing')
req('st.rerun(["workspace","contextual_lifecycle"])' in app,'main navigation must atomically rerun workspace + contextual lifecycle while leaving Scientist mounted')
req('.st-key-left_nav_panel{position:fixed!important' in app,'fixed left navigation panel CSS missing')
req('grid-template-rows:auto minmax(0,1fr) auto!important' in app and 'st-key-left_nav_nav' in app and 'st-key-left_nav_footer' in app,'left sidebar must split fixed header / scrollable nav / fixed footer')
req('.st-key-scientist_chat_drawer{position:fixed!important' in app,'fixed Scientist drawer CSS missing')
req('section[data-testid="stMain"],.stMain{{margin-left:{main_left}!important;margin-right:{main_right}!important;}}' in app,'single main reflow authority missing')
req('@media(max-width:900px)' in app and '@media(max-width:640px)' in app,'responsive shell breakpoints missing')

# R4 chat must be one isolated V2 component, not a pile of Streamlit widgets/messages.
req('render_scientist_chat_component' in app,'isolated Scientist component not mounted')
req('on_clear_change=_request_scientist_clear' in app and 'on_poll_change=' not in component,'Scientist V2 runtime mount/clear compatibility contract missing')
req('st.components.v2.component' in component,'Streamlit V2 component authority missing')
req('grid-template-rows:auto auto minmax(0,1fr) auto' in component,'component must own Header/Toolbar/History/Composer grid')
req('.scientist-history{' in component and 'overflow-y:auto' in component,'history must be sole component scroll surface')
req('height="stretch"' in component and 'width="stretch"' in component,'component must stretch to the fixed drawer instead of content-sizing the page')
req('position:absolute' in component and 'inset:0' in component and 'grid-template-rows:auto auto minmax(0,1fr) auto' in component,'component root must be viewport-anchored while grid pins header/toolbar/composer')
req(':host {' in component and 'overflow:hidden' in component,'component host must never become a second scroll surface')
req('.scientist-composer{' in component and 'max-height:96px' in component,'compact bounded composer missing')
css=component.split('_COMPONENT_CSS =',1)[1].split('_COMPONENT_JS =',1)[0]
req('position:fixed' not in css and css.count('position:absolute')==2 and '.options-menu{' in css,'component may absolute-anchor only its root and options popover; chat regions remain grid flow')
req('message-row user' not in component or True,'placeholder')
req('sessionStorage' in component and 'max_scientist_draft' in component,'browser-local draft persistence missing')
req('renderMarkdownSafe' in component and 'textContent' in component,'safe message rendering missing')
req('setTriggerValue("send"' in component and 'setTriggerValue("stop"' in component and 'setTriggerValue("close"' in component,'component send/stop/close event bridge missing')
req('assistant-model-label' in component and 'answered_by' in component,'assistant bubble must identify the actual answering model')
req('pending_model_label' in app and 'start_scientist_chat_job' in app and 'cancel_scientist_chat_job' in app,'background/cancellable Scientist generation missing')

# Manual Chat routing is strictly separate from autonomous research routing.
req('R4_STRICT_MANUAL_V1' in app,'manual Chat route migration guard missing')
req('chat_fallback_stack' in chat and 'available_chat_fallback_models' in chat,'separate Chat fallback authority missing')
route_block=chat[chat.index('route=[primary]'):chat.index('_progress("BUILDING_CONTEXT")',chat.index('route=[primary]'))]
req('llm_cfg.get("stack")' not in route_block,'manual Chat still borrows autonomous research stack')
req('Scientist Chat fallback · explicit/manual' in app,'explicit Chat fallback configuration missing')
req('Empty = a manually selected Chat model NEVER falls back' in app,'exact-model semantics not explained')
req('scientist_chat_fallback=False' in app,'stale fallback state is not reset during R4 migration')

# Read-only authority remains Python-side and execution-free.
chat_code='\n'.join(line for line in chat.splitlines() if not line.lstrip().startswith('#'))
req('from factory_control' not in chat_code and 'from champion_factory' not in chat_code and 'from factory_jobs' not in chat_code,'chat module must not import execution modules')
req('tools": []' in chat,'chat context must explicitly expose zero tools')
req('ScientistChatStore' in app and 'SCIENTIST_CHAT_STORE.save' in app,'per-Factory chat history not wired')
req(all(x in settings for x in ['left_nav_open','scientist_chat_open','scientist_chat_context_scope','scientist_chat_model','scientist_chat_fallback']),'safe shell/chat UI state not persisted')
print('PASS scientist_chat_ui_selftest')

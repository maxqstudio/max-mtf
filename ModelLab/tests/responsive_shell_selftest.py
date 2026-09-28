from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')
COMP=(ROOT/'scientist/chat/scientist_chat_component.py').read_text(encoding='utf-8')

def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS',msg)

def main():
    req(':root{' in APP and '--cp-left-w:clamp(196px,14vw,224px)' in APP,'wide shell widths are fluid, not fixed')
    req('--cp-scientist-w:clamp(336px,25vw,410px)' in APP,'Scientist width adapts on desktop')
    req('main_left="var(--cp-left-w)" if left_open else "0px"' in APP,'main left reflow follows CSS variable')
    req('main_right="var(--cp-scientist-w)" if chat_open else "0px"' in APP,'main right reflow follows CSS variable')
    req('calc(-1 * var(--cp-left-w) - 8px)' in APP,'left hide transform follows actual adaptive width')
    req('@media(max-width:1240px) and (min-width:901px)' in APP,'intermediate desktop compression breakpoint exists')
    req('@media(max-width:900px)' in APP and 'margin-left:0!important;margin-right:0!important' in APP,'tablet mode releases main workspace margins')
    req('@media(max-width:640px)' in APP and '--cp-scientist-w:100vw' in APP,'phone Scientist drawer becomes full viewport width')
    req('@media(max-height:700px)' in APP,'short-height adaptation exists')
    req('grid-template-rows:auto minmax(0,1fr) auto!important' in APP and 'st-key-left_nav_nav' in APP and 'st-key-left_nav_footer' in APP,'left sidebar has fixed header/footer with nav-only scrolling')

    # R4 Scientist internals are no longer positioned by Streamlit wrapper offsets.
    req('grid-template-rows:auto auto minmax(0,1fr) auto' in COMP,'Scientist component owns adaptive vertical grid')
    req('.scientist-history{' in COMP and 'overflow-y:auto' in COMP and 'min-height:0' in COMP,'component history is the bounded scroll region')
    req('height="stretch"' in COMP and 'width="stretch"' in COMP,'component fills drawer height instead of creating outer scrolling')
    req('position:absolute' in COMP and 'inset:0' in COMP,'component root is anchored to the drawer viewport')
    css=COMP.split('_COMPONENT_CSS =',1)[1].split('_COMPONENT_JS =',1)[0]
    req('position:fixed' not in css and css.count('position:absolute')==2,'only component root and options popover are absolute; chat regions stay grid-flow')
    req('@media(max-width:640px)' in COMP and '@media(max-height:700px)' in COMP,'component adapts to phone and short-height viewports')
    req('max-height:96px' in COMP,'composer expansion is bounded and cannot cover history')
    header_block=APP[APP.index('with st.container(key="left_nav_header")'):APP.index('with st.container(key="left_nav_nav")')]
    req('st.columns(' not in header_block,'left header no longer depends on Streamlit horizontal columns')
    req('.st-key-left_nav_hide{position:absolute!important' in APP and '.cp-side-brand{padding:.2rem 38px' in APP,'left hide control is anchored without squeezing/scrolling the brand')
    print('RESPONSIVE_SHELL_SELFTEST PASS')

if __name__=='__main__':
    main()

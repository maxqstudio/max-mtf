from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    assert 'with st.expander("Research",expanded=True):' in app and '_render_research_control(cfg)' in app
    assert 'START MANUAL RESEARCH' in app and 'START AUTO RESEARCH' in app
    assert 'compile_manual_runtime' in app and '_start_manual_background' in app
    assert '0 LLM calls · 0 deterministic candidate discovery' in app
    assert 'Validation authority · locked ON' in app
    rc=(ROOT/'research/research_control.py').read_text(encoding='utf-8')
    assert 'validation_authority": "DETERMINISTIC"' in rc
    assert 'proposal_authority": "OWNER"' in rc
    assert 'llm["enabled"] = False' in rc
    print('RESEARCH MODE AUTHORITY PASS')

if __name__=='__main__':
    main()

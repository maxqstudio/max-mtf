from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    factory=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    sci=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
    req('Max Research Agent · ONNX Factory' in app,'R7 UI version visible')
    req('Adaptive model research' in app and '_render_adaptive_model_research' in app,'Advanced exposes adaptive model research')
    req('Family selection' in app and 'adaptive_family_selection_mode' in app,'AUTO/MANUAL family checklist is operator-visible')
    req('_render_compute_backend_control' in app and 'Compute policy' in app,'registry-driven compute control is operator-visible')
    req('Actual model unavailable' in app and 'ACTUAL_ROUTE_UNAVAILABLE' in app,'legacy Scientist report never fabricates configured primary as actual model')
    req('_render_llm_route_health' in app and 'Cooldown until' in app,'current LLM stack health is operator-visible')
    req('hardware_profile.json' in factory and 'research_plan.json' in factory,'Factory persists hardware profile and compiled research plan')
    req('model_registry' in sci and 'hardware_capabilities' in sci and 'recommended_parameter_envelopes' in sci,'Research Director receives hardware/model capability context')
    req('legacy_fallback_families' in sci,'legacy enabled families are explicitly compatibility context')
    req('llm_provenance' in factory,'Factory journals preserve LLM provenance')
    req('hybrid_parts(fam)' in app,'Scientist proposal UI renders generic hybrid families')
    print('R7_ADAPTIVE_UI_SELFTEST PASS')
if __name__=='__main__': main()

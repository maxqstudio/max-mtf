from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def sha(name: str) -> str:
    return hashlib.sha256((ROOT/name).read_bytes()).hexdigest()


def section(text: str, start: str, end: str | None = None) -> str:
    i=text.index(start)
    if end is None:
        return text[i:]
    j=text.index(end,i+len(start))
    return text[i:j]


def main():
    import sys
    sys.path.insert(0,str(ROOT))
    from models.model_inspector import candidate_detail, parameter_groups

    # Scientific/search/evaluation authority must remain byte-identical to v1.4.4.
    frozen={
        'kpi.py':'274ad08001c9050156525661a84f3c26209858d2568010dbf07701b2e7dd66f6',
        'cpcv.py':'4358259d7eed365860d1b6ac331683b1ae168c5385197b67b70e66bb4f508d13',
        'champion_factory.py':'e3487461916baa3375589c9759583e0ce2e64753d3c56f9d869e154dbf5b0732',
        'risk_kpi.py':'c09b2dacea4b06f5aea4dea2588778bf7c437e25fc432c8ef72dd97ec6083b2d',
        'sample_policy.py':'f461061ba21530d5b5fb005e44662ee7332b0d0dea72349ff7266aada33e616e',
        'models.py':'e6b98b3864e999114bd45b2adc1de8bf049a07674520c9ea2bd38b7960c853bd',
        'supervisor_agent.py':'f6fcaf234681eb1cd1784149c77371aa2d168ce9297d83f0f1739e74a8ed24c6',
        'research_architect.py':'661b6ac67de1eaca5508aaa9715d57721be553c6db58e72b8397244a48cca047',
        'model_registry.py':'d4b5b86d6ba6e3c9c8267afd11f78bfbf653cfab2f16680cbde7888dabbf0520',
        'factory_jobs.py':'78c1791b00fdb7ffcc7db476ed3b7ea423c38044c803b936d5c535ec4edddd23',
        'strategy_optimizer_jobs.py':'08be201b6fc65569ce43372758c4e9da1c3bc775b62fb85321b3fb982ce86a99',
    }
    for name,digest in frozen.items():
        req(sha(name)==digest,f'v1.4.5 observability repair leaves {name} scientific/runtime authority byte-identical to v1.4.4')

    with tempfile.TemporaryDirectory() as td:
        fd=Path(td)/'FACTORY_TEST'; fd.mkdir()
        gru_params={
            'sequence_length':64,'hidden_size':32,'num_layers':1,'dropout':0.0,
            'learning_rate':0.001,'batch_size':32,'epochs':10,'weight_decay':0.0,
            'training_memory_months':12,
        }
        tree_params={
            'n_estimators':100,'max_depth':4,'learning_rate':0.05,'subsample':0.8,
            'colsample_bytree':0.8,'min_child_weight':1.0,'reg_lambda':1.0,'reg_alpha':0.0,
            'training_memory_months':12,
        }
        hybrid_params={
            **{f'temporal_{k}':v for k,v in gru_params.items()},
            **{f'policy_{k}':v for k,v in tree_params.items()},
        }
        trials=[
            {'schema':'TEST','trial_stage':'FULL_WFA','name':'gru_candidate','family':'gru','params':gru_params,'full_params':gru_params,'training_seed':42},
            {'schema':'TEST','trial_stage':'FULL_WFA','name':'tree_candidate','family':'xgboost','params':tree_params,'full_params':tree_params,'training_seed':42},
            {'schema':'TEST','trial_stage':'FULL_WFA','name':'hybrid_candidate','family':'hybrid::gru::xgboost','params':hybrid_params,'full_params':hybrid_params,'training_seed':42},
        ]
        (fd/'all_trials.jsonl').write_text('\n'.join(json.dumps(x,sort_keys=True) for x in trials)+'\n',encoding='utf-8')

        d=candidate_detail(factory_dir=fd,row={'Model':'gru_candidate','Family':'gru'})
        req(d['parameters']==gru_params,'inspector resolves exact frozen neural candidate parameters from committed trial evidence')
        req(isinstance(d['parameter_count'],int) and d['parameter_count']>0,'inspector reports executable trainable parameter count for neural candidate')
        req(d['parameter_count_scope']=='EXECUTABLE_ARCHITECTURE','neural count is explicitly scoped as executable architecture, not guessed fitted evidence')
        req(len(parameter_groups('gru',d['parameters']))==len(gru_params),'inspector renders every stored neural setup parameter')

        t=candidate_detail(factory_dir=fd,row={'Model':'tree_candidate','Family':'xgboost'})
        req(t['parameter_count'] is None and t['parameter_count_scope']=='TREE_STRUCTURE_DATA_DEPENDENT','tree model never fabricates neural-style parameter count')
        req(t['tree_complexity'].get('n_estimators')==100 and t['tree_complexity'].get('max_depth')==4,'tree inspector exposes frozen tree capacity setup')
        req(t['tree_complexity'].get('structural_node_upper_bound')==3100,'tree inspector exposes deterministic structural node upper bound without claiming fitted node count')

        h=candidate_detail(factory_dir=fd,row={'Model':'hybrid_candidate','Family':'hybrid::gru::xgboost'})
        req(isinstance(h['parameter_count'],int) and h['parameter_count']>0,'hybrid inspector reports exact executable temporal-leg trainable parameter count')
        req(h['tree_complexity'].get('n_estimators')==100,'hybrid inspector also exposes frozen tree-policy complexity')
        req(h['parameters']==hybrid_params,'hybrid inspector preserves exact temporal+policy parameter setup')

    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('\"selection_mode\":\"single-row\"' in app and '\"on_select\":\"rerun\"' in app,'shared model table uses one-row click selection and remains UI-only')
    req('MAX_MODEL_DETAIL_INSPECTOR_V1' in (ROOT/'models/model_inspector.py').read_text(encoding='utf-8'),'read-only model inspector has explicit provenance schema')
    inspector=(ROOT/'models/model_inspector.py').read_text(encoding='utf-8')
    req('.write_text(' not in inspector and '.write_bytes(' not in inspector and 'unlink(' not in inspector,'model inspector cannot mutate research evidence')

    coverage={
        '_render_research_live_summary':'research_live_summary_',
        '_render_factory_job_monitor':'live_factory_models_',
        '_render_discovery_stage':'discovery_near_miss_',
        '_render_pool_stage':'pool_models_',
        '_render_cpcv_live_inspector':'cpcv_models_',
        '_render_tournament_stage':'tournament_models_',
        '_render_monte_carlo_stage':'monte_carlo_models_',
        '_render_forward_stage':'forward_models_',
        '_render_model_challenger_registry':'model_challenger_models',
        '_render_model_champion_summary':'model_champion_current',
        '_render_model_champion_stage':'factory_winner_model_',
    }
    defs=list(coverage)
    for i,name in enumerate(defs):
        start='def '+name+'('
        # nearest later def is sufficient for static coverage guard.
        pos=app.index(start)
        next_pos=app.find('\ndef ',pos+len(start))
        body=app[pos:] if next_pos<0 else app[pos:next_pos]
        req(coverage[name] in body,f'{name} is wired to the reusable selectable Model Detail Inspector')

    req('@st.fragment(run_every="2s", key="factory_job_live_monitor")\ndef _render_factory_job_monitor' in app,'Discovery/Factory live model monitor polls committed evidence every 2 seconds')
    req('@st.fragment(run_every="2s", key="contextual_lifecycle")' in app,'contextual Research/Optimizer sidebar lifecycle polls every 2 seconds')
    req('@st.fragment(run_every=2.0)\n    def _strategy_optimizer_status' in app,'Strategy Optimizer main runtime status polls every 2 seconds')

    research_body=section(app,'def _render_global_research_controls_body','def _render_discovery_stage')
    optimizer_body=section(app,'def _render_global_optimizer_controls_body','def _render_global_research_controls_body')
    req('_live_status_strip(' in research_body and 'cp-busy-row' not in research_body,'Research sidebar loading status is flat and no longer rendered as a card')
    req('_live_status_strip(' in optimizer_body and 'cp-busy-row' not in optimizer_body,'Optimizer sidebar loading status is flat and no longer rendered as a card')
    req('.st-key-global_optimizer_lifecycle' in app and '.st-key-global_research_lifecycle' in app and '.cp-live-status' in app,'Research + Optimizer lifecycle wrappers are explicitly borderless/transparent')
    req('cp-side-build">v1.4.5</span>' in app,'visible sidebar build identity is v1.4.5')

    print('V145_MODEL_INSPECTOR_LIVE_RUNTIME_SELFTEST PASS')


if __name__=='__main__':
    main()

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scientist.skills.max_scientist_skills import load_manifest, skill_guidance
from research.structured_research_memory import (
    EXPERIENCE_SCHEMA,
    SCHEMA,
    canonical_stage,
    hypothesis_to_experience,
    refresh_structured_memory,
    stage_learning_zone,
)

ROOT=Path(__file__).resolve().parents[1]


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def hyp(stage='DISCOVERY', status='SUPPORTED'):
    return {
        'hypothesis_id':'H_RICH_1',
        'parent_id':'H_PARENT',
        'kind':'MODEL_ARCHITECTURE',
        'title':'bounded capacity repair',
        'rationale':'test whether under-capacity explains the blocker',
        'expected_observation':'worst fold improves without coverage collapse',
        'payload':{
            'families':['gru'],
            'family_priorities':{'gru':1.2},
            'variable_keys_by_family':{'gru':['hidden_size']},
            'parameter_ranges_by_family':{'gru':{'hidden_size':[16,32]}},
        },
        'status':status,
        'source':'SCIENTIST',
        'source_stage':stage,
        'source_generation':3,
        'source_failure_gate':'CV_WORST_EXPECTANCY',
        'source_failure_topology':{
            'dominant_first_failed_gate':'CV_WORST_EXPECTANCY',
            'first_failed_gate_counts':{'CV_WORST_EXPECTANCY':3},
            'worst_split_combination':{'test_groups':[1,4],'median_expectancy_r':-0.04},
        },
        'observations':[{
            'block_id':'GEN03-HRICH-01',
            'candidate_ids':['C_A','C_B'],
            'coverage':{'candidate_count':2,'total_validation_trades':240},
            'failure_margins':{'best_closest_relative_margin':-0.02},
            'fold_distribution':{'worst_fold_expectancy_r':0.01},
            'scientific_interpretation':'lower-tail blocker improved',
        }],
        'decisive_outcome':{
            'stage':'CPCV',
            'reason':'ORIGINATING_GATE_CLEARED_BUT_STAGE_STILL_FAILED',
            'matching_candidate_ids':['C_A'],
            'coverage':{'candidate_count':1},
        },
    }


def main():
    protected=('FRESH','FRESH_FORWARD','FORWARD','FORWARD_CHAMPIONSHIP','LOCKED','LOCKED_TEST','LOCKED_OOS','SHADOW','PROMOTION','CHAMPION','MODEL_CHAMPION','FACTORY_WINNER','ELIGIBLE_CHALLENGER')
    for stage in protected:
        req(stage_learning_zone(stage)=='PROTECTED',f'{stage} canonicalizes to protected learning zone')
        req(hypothesis_to_experience(hyp(stage=stage)) is None,f'{stage} cannot enter adaptive research experience')
    req(canonical_stage('LOCKED_TEST')=='LOCKED_OOS','LOCKED_TEST alias canonicalizes to LOCKED_OOS')
    req(canonical_stage('FRESH')=='FRESH_FORWARD','FRESH alias canonicalizes to FRESH_FORWARD')
    req(stage_learning_zone('UNREGISTERED_FUTURE_STAGE')=='UNKNOWN','unknown stage classification is explicit')
    req(hypothesis_to_experience(hyp(stage='UNREGISTERED_FUTURE_STAGE')) is None,'unknown stage fails closed from adaptive memory')
    req(hypothesis_to_experience(hyp(stage='DISCOVERY')) is not None,'known adaptive Discovery evidence remains learnable')
    req(hypothesis_to_experience(hyp(stage='CPCV')) is not None,'known validation CPCV post-mortem evidence remains learnable')

    rich=hypothesis_to_experience(hyp())
    req(rich['schema']==EXPERIENCE_SCHEMA and rich['parent_id']=='H_PARENT','V2 experience preserves parent lineage when supplied')
    req(rich['experiment_id']=='GEN03-HRICH-01' and rich['candidate_ids']==['C_A','C_B'],'V2 experience preserves experiment/candidate lineage')
    req(rich['hyperparameters']['parameter_ranges_by_family']['gru']['hidden_size']==[16,32],'V2 experience preserves bounded hyperparameter action')
    req(rich['state_before']['dominant_first_failed_gate']=='CV_WORST_EXPECTANCY','V2 experience preserves state-before failure topology')
    req(rich['failed_gates'][0]=='CV_WORST_EXPECTANCY','V2 experience preserves failed-gate topology')
    req(rich['fold_distribution'] is not None and rich['coverage'] is not None,'V2 experience preserves fold/coverage evidence when supplied')
    req(rich['predicted_effect']=='worst fold improves without coverage collapse','V2 experience preserves predeclared prediction')

    poisoned={
        'schema':'CP_RESEARCH_MEMORY_V1',
        'experience_ledger':[
            {'schema':'MAX_RESEARCH_EXPERIENCE_V1','experience_id':'EXP_POISON','hypothesis_id':'OLD','action_kind':'FEATURE_ABLATION','status':'SUPPORTED','source_stage':'FRESH','source_failure_gate':'X','protected_evidence_used':False},
            {'schema':'MAX_RESEARCH_EXPERIENCE_V1','experience_id':'EXP_SAFE','hypothesis_id':'SAFE','action_kind':'FEATURE_ABLATION','status':'SUPPORTED','source_stage':'DISCOVERY','source_failure_gate':'X','protected_evidence_used':False},
        ]
    }
    cleaned=refresh_structured_memory(poisoned,[])
    ids={x['experience_id'] for x in cleaned['experience_ledger']}
    req('EXP_POISON' not in ids and 'EXP_SAFE' in ids,'refresh purges protected legacy ledger rows while retaining admissible evidence')
    req(cleaned['structured_memory_schema']==SCHEMA and cleaned['learning_stage_contract']['unknown_stage_policy']=='REJECT','structured memory publishes explicit fail-closed stage contract')

    manifest=load_manifest(verify=True)
    req(all('## TEST / REGRESSION FIXTURES' in (ROOT/r['file']).read_text(encoding='utf-8') for r in manifest['skills']),'every Scientist skill carries regression fixtures')
    g=skill_guidance({'failure_topology':{'dominant_first_failed_gate':'CV_MIN_TRADES'},'top_results':[{'name':'A'}]})
    req(g.get('method_context_mode')=='SELECTED_SKILL_PROCEDURES_NOT_SUMMARY_ONLY','runtime skill context is full selected methodology, not doctrine-only')
    req(len(g.get('methods') or [])==len(g['skill_ids']),'every selected skill supplies runtime methodology')
    required={'PURPOSE','INPUT EVIDENCE','DECISION PROCEDURE','FAILURE PATTERNS','ALLOWED ACTIONS','FORBIDDEN ACTIONS','OUTPUT SCHEMA','TEST / REGRESSION FIXTURES'}
    req(all(required.issubset(set(x.get('methodology') or {})) and all(str(v).strip() for v in (x.get('methodology') or {}).values()) for x in g['methods']),'runtime methodology includes all required decision sections')

    import json
    pkg=ROOT.parent
    registry=json.loads((pkg/'governance/EXTERNAL_RUNTIME_GATES.json').read_text(encoding='utf-8'))
    manifest=json.loads((pkg/'governance/PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    current=json.loads((pkg/'governance/CURRENT_AUTHORITY.json').read_text(encoding='utf-8'))
    req(registry.get('schema')=='MAX_EXTERNAL_RUNTIME_GATES_V1' and registry.get('authority')=='SINGLE_CANONICAL_EXTERNAL_RUNTIME_GATE_REGISTRY' and len(registry.get('gates') or [])>=12,'canonical external runtime gate registry is present and complete')
    req(manifest.get('external_gates')==registry.get('gates') and manifest.get('external_gates_registry')=='governance/EXTERNAL_RUNTIME_GATES.json','package manifest consumes the canonical external runtime gate set')
    req(current.get('external_gates_registry')=='governance/EXTERNAL_RUNTIME_GATES.json','CURRENT_AUTHORITY points to the canonical external runtime gate registry')
    req(not any(str(x.get('status') or '').upper()=='PASS' for x in registry.get('gates') or []),'canonical external runtime registry cannot pre-promote runtime gates to PASS')
    runacc=(ROOT/'acceptance/runners/run_acceptance.py').read_text(encoding='utf-8')
    req("GOV/'EXTERNAL_RUNTIME_GATES.json'" in runacc and "'external_gates':_external_gates()" in runacc,'build acceptance reads external gates from the canonical registry')

    print('V141_AGENTIC_LEARNING_AUDIT_REPAIR_SELFTEST PASS')


if __name__=='__main__':
    main()

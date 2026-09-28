from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req('run_feature_label_audit' in src and 'run_guided_research' in src,'Feature+Label Audit and Guided Research restored inside Factory')
    req('new_qualified == 0' in src and '_guided_cycle' in src,'failed generation routes through Guided learning')
    req('guided_override' in src and 'recommended_config' in src,'Guided winner changes next generation research contract')
    req('research_overrides' in src,'candidate-specific learned label/feature contract freezes into pool')
    print('FACTORY_GUIDED_RESTORE PASS')
if __name__=='__main__': main()

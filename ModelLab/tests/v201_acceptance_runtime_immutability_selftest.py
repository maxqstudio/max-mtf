from pathlib import Path
import hashlib,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)

def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

critical=[ROOT/'runtime/active_release.json',ROOT/'runtime/strategy_authority.json',ROOT/'runtime/strategy_challenger_registry.json']
before={str(p):sha(p) for p in critical}
cp=subprocess.run([sys.executable,str(ROOT/'tests/v200_zero_champion_lifecycle_selftest.py')],cwd=ROOT,env={**__import__('os').environ,'PYTHONPATH':str(ROOT)})
req(cp.returncode==0,'zero-Champion selftest must pass in sandbox')
after={str(p):sha(p) for p in critical}
req(before==after,'acceptance selftest must not mutate packaged runtime authorities')
source=(ROOT/'acceptance/runners/run_acceptance.py').read_text(encoding='utf-8')
req('_runtime_authority_signature' in source and 'ACCEPTANCE_RUNTIME_AUTHORITY_MUTATED' in source,'acceptance runner must enforce runtime-authority immutability after every gate')
print('V201_ACCEPTANCE_RUNTIME_IMMUTABILITY PASS')

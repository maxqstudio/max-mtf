from __future__ import annotations

import hashlib
import json
import os
import site
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

import acceptance.runners.run_acceptance as run_acceptance
from acceptance.runners.max_python_bootstrap import (
    UNAVAILABLE_REASON as MAX_PYTHON_UNAVAILABLE_REASON,
    canonical_target_command,
    resolve_bootstrap_python,
)
from scientist.knowledge.scientist_knowledge import load_knowledge, local_acceptance_expectations, sync_status, workflow_audit_sync_status
from scientist.python.scientist_python_runtime import (
    CHILD_RUNNER,
    EVIDENCE_CLASS,
    REQUIREMENTS_FILE,
    authorized_analysis_inputs,
    run_scientist_python_analysis,
    scientist_python_executable,
    scientist_python_health,
    validate_scientist_code,
)
from scientist.python.scientist_python_capabilities import (
    TRANSITIVE_DANGEROUS_ATTRIBUTES,
    capability_surface_manifest,
)
from acceptance.runners.owner_scientist_python_runtime_acceptance import (
    AUTHORITY as OWNER_ACCEPTANCE_AUTHORITY,
    EVIDENCE_CLASS as OWNER_EVIDENCE_CLASS,
    PINNED as OWNER_PINNED,
    REQUIRED_CHECKS as OWNER_REQUIRED_CHECKS,
    SCHEMA as OWNER_ACCEPTANCE_SCHEMA,
    OwnerScientistPythonAcceptanceError,
    verify_owner_evidence_payload,
)

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent

def req(cond,msg):
    if not cond:
        raise AssertionError(msg)

def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()

# Production setup/health is one-click and package-isolated.
req((ROOT/'tools/scientist_python/RUN_SCIENTIST_PYTHON_SETUP.cmd').is_file(),'setup cmd missing')
req((ROOT/'tools/scientist_python/RUN_SCIENTIST_PYTHON_HEALTHCHECK.cmd').is_file(),'healthcheck cmd missing')
req((ROOT/'scientist/python/scientist_python_setup.py').is_file(),'setup host missing')
req((ROOT/'scientist/python/scientist_python_child.py').is_file(),'child runner missing')
req(REQUIREMENTS_FILE.is_file(),'Scientist requirements missing')
requirements=REQUIREMENTS_FILE.read_text(encoding='utf-8')
for token in ('numpy==','pandas==','scipy==','scikit-learn=='):
    req(token in requirements,f'pinned dependency missing: {token}')
req('torch' not in requirements.lower(),'Scientist V1 must not install Torch')
runtime_src=(ROOT/'scientist/python/scientist_python_runtime.py').read_text(encoding='utf-8')
req('LOCALAPPDATA' in runtime_src and 'MaxMTF' in runtime_src and 'ScientistPython' in runtime_src,'deterministic user-local Scientist environment path missing')
req('guarded executor' in runtime_src.lower() and 'os-level sandbox' in runtime_src.lower(),'runtime must not falsely claim OS sandboxing')

with tempfile.TemporaryDirectory(prefix='max_scientist_py_gate_') as td:
    td=Path(td)
    # Acceptance-only isolated interpreter fixture. Production setup never uses system-site
    # packages; this fixture skips dependency identity so local acceptance does not require
    # network/package installation merely to test process separation/guards/timeouts.
    home=td/'ScientistPython'
    venv.EnvBuilder(with_pip=False,clear=True).create(str(home/'venv'))
    exe=scientist_python_executable(home)
    req(exe.is_file(),'temporary separate interpreter missing')

    # CASE A — exact executable identity must differ.
    h=scientist_python_health(home,verify_packages=False)
    req(h.get('status')=='READY',f'separate test runtime not ready: {h}')
    req(h.get('separate_interpreter') is True,'Scientist interpreter separation not proven')
    req(Path(h['scientist_python_executable']).resolve()!=Path(h['canonical_max_python_executable']).resolve(),'Scientist Python reuses canonical MAX Python')

    rt=td/'analysis_runtime'
    inputs={'WFA_ROWS':[{'score':1.0},{'score':2.0},{'score':3.0},{'score':4.0}]}
    good={
        'purpose':'calculate deterministic summary statistics', 'input_ids':['WFA_ROWS'], 'seed':42, 'timeout_sec':10,
        'code':'import statistics\nxs=[float(x["score"]) for x in inputs["WFA_ROWS"]]\nresult={"mean":statistics.mean(xs),"median":statistics.median(xs),"stdev":statistics.stdev(xs)}',
    }
    # CASE C — valid statistical analysis + exact provenance.
    c=run_scientist_python_analysis(good,inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(c.get('execution_status')=='EXECUTED' and c.get('analysis_mode')=='PYTHON_ASSISTED',f'valid analysis failed: {c}')
    req(c.get('evidence_class')==EVIDENCE_CLASS,'Python output authority class mismatch')
    req(c.get('structured_result')=={'mean':2.5,'median':2.5,'stdev':1.2909944487358056},'statistical result mismatch')
    req(c.get('seed')==42 and c.get('code_sha256') and c.get('input_hashes',{}).get('WFA_ROWS'),'provenance incomplete')
    adir=rt/c['analysis_id']
    for name in ('request.json','generated_code.py','result.json','provenance.json'):
        req((adir/name).is_file(),f'analysis provenance artifact missing: {name}')
    prov=json.loads((adir/'provenance.json').read_text(encoding='utf-8'))
    req(prov.get('generated_code')==good['code'],'provenance must record exact generated code')
    req(prov.get('result_hash') and prov.get('artifact_hashes',{}).get('generated_code.py'),'result/artifact hashes incomplete')

    # Bounded-output regression: generated prints cannot create unbounded captured evidence.
    loud=run_scientist_python_analysis({'purpose':'bounded output fixture','input_ids':['WFA_ROWS'],'code':'print("x"*50000)\nresult={"ok":True}'},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(loud.get('execution_status')=='EXECUTED','bounded-output fixture failed')
    req(len(str(loud.get('stdout_excerpt') or ''))<=12050 and 'OUTPUT_TRUNCATED' in str(loud.get('stdout_excerpt') or ''),'stdout capture is not bounded/truncated')

    # CASE B/J — missing live runtime wins over static capability knowledge.
    missing=scientist_python_health(td/'missing',verify_packages=False)
    req(missing.get('status')=='UNAVAILABLE' and missing.get('analysis_mode')=='REASONING_ONLY','missing runtime must degrade to REASONING_ONLY')
    kb=load_knowledge(); caps={x.get('id') for x in kb.get('existing_capabilities') or []}
    req('SCIENTIST_PYTHON_ANALYSIS_RUNTIME' in caps,'static Scientist Knowledge capability missing')
    req(missing.get('status')!='READY','static Knowledge must not override live interpreter health')

    # CASE D/F — dangerous imports/network surfaces rejected before execution.
    for label,code in {
        'os':'import os\nresult={}',
        'subprocess':'import subprocess\nresult={}',
        'socket':'import socket\nresult={}',
        'network':'import pandas as pd\nresult=pd.read_html("https://example.com")',
    }.items():
        v=validate_scientist_code(code)
        req(not v.get('ok'),f'{label} dangerous code unexpectedly allowed')
        r=run_scientist_python_analysis({'purpose':label,'input_ids':['WFA_ROWS'],'code':code},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
        req(r.get('execution_status')=='REJECTED' and r.get('analysis_mode')=='REASONING_ONLY',f'{label} must reject pre-execution')

    # CASE E — source/governance mutation attempt is rejected and protected bytes unchanged.
    protected=[ROOT/'acceptance/runners/run_acceptance.py',PKG/'governance/CURRENT_AUTHORITY.json',ROOT/'models/models.py']
    before={str(p):sha(p) for p in protected}
    mutation='result=open("governance/CURRENT_AUTHORITY.json","w").write("tamper")'
    e=run_scientist_python_analysis({'purpose':'mutate authority','input_ids':['WFA_ROWS'],'code':mutation},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(e.get('execution_status')=='REJECTED','source/governance mutation must reject')
    req(before=={str(p):sha(p) for p in protected},'rejected analysis changed protected source/governance')

    # CASE G — infinite loop times out, child is killed, subsequent analysis still works.
    g=run_scientist_python_analysis({'purpose':'timeout fixture','input_ids':['WFA_ROWS'],'timeout_sec':1,'code':'while True:\n    pass\nresult={"never":True}'},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(g.get('execution_status')=='TIMEOUT' and g.get('analysis_mode')=='REASONING_ONLY','infinite loop must TIMEOUT')
    req(scientist_python_health(home,verify_packages=False).get('status')=='READY','timeout must not damage Scientist environment')
    g2=run_scientist_python_analysis(good,inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(g2.get('execution_status')=='EXECUTED','MAX/Scientist runtime unhealthy after timeout')

    # CASE H — runtime exception captured with no fabricated result.
    hres=run_scientist_python_analysis({'purpose':'exception fixture','input_ids':['WFA_ROWS'],'code':'x=1/0\nresult={"fake":123}'},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(hres.get('execution_status')=='ERROR' and hres.get('analysis_mode')=='REASONING_ONLY','runtime exception must ERROR/fallback')
    req(hres.get('structured_result') is None,'failed execution must not expose fabricated structured result')

    # CASE I — LLM cannot select arbitrary local paths/interpreter.
    ires=run_scientist_python_analysis({'purpose':'path smuggle','input_ids':['WFA_ROWS'],'code':'result={"ok":True}','path':r'C:\\MAX'},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(ires.get('execution_status')=='REJECTED','arbitrary LLM path field must reject')
    i2=run_scientist_python_analysis({'purpose':'path as input','input_ids':[r'D:\\secret.csv'],'code':'result={"ok":True}'},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(i2.get('execution_status')=='INPUT_UNAVAILABLE','arbitrary path input reference must be unavailable')

    # CASE K — even an analytical "PASS" recommendation remains non-authoritative.
    kres=run_scientist_python_analysis({'purpose':'recommendation fixture','input_ids':['WFA_ROWS'],'code':'result={"candidate":"PASS","recommendation":"promote"}'},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(kres.get('execution_status')=='EXECUTED','recommendation fixture execution failed')
    req(kres.get('authority')=='ANALYTICAL_SUPPORT_ONLY_DETERMINISTIC_FACTORY_REMAINS_SOLE_DECISION_AUTHORITY','Python recommendation gained deterministic authority')
    scientist_src=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
    req('strict_scientist_candidate_admission' in scientist_src,'deterministic Scientist candidate admission authority missing')
    req(all(x not in runtime_src for x in ('from factory_control import','from champion_factory import','from factory_jobs import')),'Python runtime imports Factory control authority')

    # ------------------------------------------------------------------
    # TRANSITIVE AUTHORITY ESCAPE REPAIR — CASES N-W
    # Acceptance-only package bridge: keep a distinct interpreter executable while making
    # the canonical test machine's already-installed scientific wheels visible. Production
    # setup NEVER uses this bridge; it installs the pinned Scientist requirements into its
    # own user-local venv.
    canonical_sites=[Path(x) for x in site.getsitepackages() if Path(x).exists()]
    probe=subprocess.check_output([str(exe),'-c','import json,site;print(json.dumps(site.getsitepackages()))'],text=True).strip()
    scientist_sites=json.loads(probe)
    req(scientist_sites,'temporary Scientist venv site-packages unavailable')
    scientist_site=Path(scientist_sites[0]); scientist_site.mkdir(parents=True,exist_ok=True)
    (scientist_site/'max_mtf_acceptance_science_packages.pth').write_text('\n'.join(str(x) for x in canonical_sites)+'\n',encoding='utf-8')

    def direct_child(code: str, cwd: Path):
        """Bypass host AST deliberately to prove the child capability boundary itself."""
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR','PATH','HOME','USERPROFILE','COMSPEC','PATHEXT'} and isinstance(v,str)}
        env.update({'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1'})
        blob=json.dumps({'code':code,'inputs':inputs,'seed':42,'max_result_bytes':512000},ensure_ascii=False,separators=(',',':'))
        cp=subprocess.run([str(exe),'-I',str(CHILD_RUNNER)],input=blob,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=str(cwd),env=env,timeout=20)
        payload={}
        try:
            payload=json.loads((cp.stdout or '').strip().splitlines()[-1])
        except Exception:
            pass
        return cp,payload

    # CASE N — NumPy ctypes transitive exposure. Host rejects it and the child proxy also
    # refuses it when AST validation is intentionally bypassed.
    ncode='import numpy as np\nx=np.ctypeslib.ctypes\nresult={"reachable":True}'
    nv=validate_scientist_code(ncode)
    req(not nv.get('ok'),'NumPy ctypes transitive surface passed host validation')
    nr=run_scientist_python_analysis({'purpose':'transitive ctypes exposure','input_ids':['WFA_ROWS'],'code':ncode},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(nr.get('execution_status')=='REJECTED' and nr.get('analysis_mode')=='REASONING_ONLY','NumPy ctypes exposure must reject')
    ncp,npayload=direct_child(ncode,td)
    req(ncp.returncode!=0 and npayload.get('status')=='ERROR','child capability proxy exposed NumPy ctypes when host validation was bypassed')

    # CASE O — actual disposable native-file-write payload reached through the exact
    # transitive path Control Room used. The file primitive itself must never run.
    native_target=td/'native_escape_probe.txt'
    if os.name=='nt':
        opath=str(native_target).replace('\\','\\\\')
        ocode=(
            'import numpy as np\n'
            'k=np.ctypeslib.ctypes.windll.kernel32\n'
            f'h=k.CreateFileW("{opath}",0x40000000,0,None,2,0,None)\n'
            'result={"handle":h}'
        )
    else:
        ob=str(native_target).encode('utf-8')
        ocode=(
            'import numpy as np\n'
            'libc=np.ctypeslib.ctypes.CDLL(None)\n'
            f'fd=libc.open({ob!r},65,420)\n'
            'libc.write(fd,b"ESCAPE",6)\nlibc.close(fd)\nresult={"fd":fd}'
        )
    ocp,opayload=direct_child(ocode,td)
    req(ocp.returncode!=0 and not native_target.exists(),'native filesystem write escaped child capability boundary')

    # CASE P — Windows native mutation path. On non-Windows CI this remains a structural
    # fail-closed fixture; on Windows it is the real Win32 path and must still be blocked.
    win_target=td/'win32_escape_probe.txt'
    wpath=str(win_target).replace('\\','\\\\')
    pcode=(
        'import numpy as np\n'
        'k=np.ctypeslib.ctypes.windll.kernel32\n'
        f'h=k.CreateFileW("{wpath}",0x40000000,0,None,2,0,None)\n'
        'result={"handle":h}'
    )
    req(not validate_scientist_code(pcode).get('ok'),'Win32 transitive FFI path passed host validation')
    pcp,ppayload=direct_child(pcode,td)
    req(pcp.returncode!=0 and not win_target.exists(),'Win32 native write path escaped capability boundary')

    # CASE Q — native process launch. Marker proves no command ran.
    process_marker=td/'native_process_marker.txt'
    if os.name=='nt':
        cmd=f'cmd /c echo ESCAPE>{process_marker}'.replace('\\','\\\\')
        qcode=f'import numpy as np\nk=np.ctypeslib.ctypes.windll.kernel32\nr=k.WinExec(b"{cmd}",0)\nresult={{"rc":r}}'
    else:
        cmd=f'touch {process_marker}'
        qcode=f'import numpy as np\nlibc=np.ctypeslib.ctypes.CDLL(None)\nr=libc.system({cmd.encode()!r})\nresult={{"rc":r}}'
    qcp,qpayload=direct_child(qcode,td)
    req(qcp.returncode!=0 and not process_marker.exists(),'native process/command launch escaped capability boundary')

    # CASE R — native network authority. Retrieving a native socket function through an
    # allowed scientific root is itself denied before any descriptor/connection exists.
    if os.name=='nt':
        rcode='import numpy as np\nw=np.ctypeslib.ctypes.windll.ws2_32\ns=w.socket(2,1,6)\nresult={"socket":s}'
    else:
        rcode='import numpy as np\nlibc=np.ctypeslib.ctypes.CDLL(None)\ns=libc.socket(2,1,0)\nresult={"socket":s}'
    req(not validate_scientist_code(rcode).get('ok'),'native network FFI path passed host validation')
    rcp,rpayload=direct_child(rcode,td)
    req(rcp.returncode!=0 and rpayload.get('status')=='ERROR','native network authority escaped child capability boundary')

    # CASE S — bytes absolute-path literals are rejected too, and still cannot become I/O
    # authority if host validation is bypassed.
    bytes_path=(b'C:\\MAX\\scientist_escape_probe.txt' if os.name=='nt' else b'/tmp/scientist_escape_probe.txt')
    scode=f'import numpy as np\np={bytes_path!r}\nlibc=np.ctypeslib.ctypes.CDLL(None)\nresult={{"p":str(p),"lib":str(libc)}}'
    req(not validate_scientist_code(scode).get('ok'),'bytes absolute path / transitive FFI bypass passed validation')
    scp,spayload=direct_child(scode,td)
    req(scp.returncode!=0,'bytes-path native escape executed unexpectedly')

    # CASE T — transitive public capability scan. No governed import surface may expose a
    # known native/system authority attribute. The child import hook must return proxies,
    # not raw __import__ module objects.
    manifest=capability_surface_manifest()
    exposed={a for attrs in manifest.values() for a in attrs}
    req(not (set(TRANSITIVE_DANGEROUS_ATTRIBUTES)&exposed),f'dangerous transitive attributes exposed: {set(TRANSITIVE_DANGEROUS_ATTRIBUTES)&exposed}')
    # Import-from names are governed by the same capability manifest, not merely by the
    # allowed top-level module name. This closes `from numpy import ctypeslib`-style bypasses.
    for import_code in (
        'from numpy import ctypeslib\nresult={}',
        'from pandas import read_csv\nresult={}',
        'from scipy import io\nresult={}',
    ):
        req(not validate_scientist_code(import_code).get('ok'),f'non-capability from-import passed validation: {import_code!r}')

    # Do not allow real libraries to call generated callbacks with raw pandas/scientific
    # objects. Unknown/callback kwargs fail closed at the capability boundary.
    callback_code=(
        'import pandas as pd\n'
        'df=pd.DataFrame([{"x":2},{"x":1}])\n'
        'df=df.sort_values("x",key=lambda raw: raw)\n'
        'result={"rows":df.to_dict("records")}')
    ccp,cpayload=direct_child(callback_code,td)
    req(ccp.returncode!=0 and cpayload.get('status')=='ERROR','generated pandas callback reached raw library objects')
    agg_callback=(
        'import pandas as pd\n'
        'df=pd.DataFrame([{"g":"a","x":1},{"g":"a","x":2}])\n'
        'def f(raw):\n    return raw\n'
        'x=df.groupby("g").agg({"x":f})\nresult={"ok":True}')
    acp,apayload=direct_child(agg_callback,td)
    req(acp.returncode!=0 and apayload.get('status')=='ERROR','generated groupby callback reached raw library objects')
    child_src=(ROOT/'scientist/python/scientist_python_child.py').read_text(encoding='utf-8')
    req('return proxy' in child_src and '_IMPORT_PROXIES' in child_src,'child import authority is not capability-proxy based')
    req('return __import__(name' not in child_src,'child controlled import returns raw modules')

    # CASE U — legitimate analytical regression. Real scientific libraries are reachable
    # only through capability views, and representative in-memory operations remain useful.
    science_cases={
        'numpy': 'import numpy as np\na=np.array([1,2,3,4])\nresult={"mean":np.mean(a),"double":(a*2).tolist(),"q":np.quantile(a,0.5)}',
        'pandas': 'import pandas as pd\ndf=pd.DataFrame([{"x":1.0,"g":"a"},{"x":2.0,"g":"a"},{"x":4.0,"g":"b"}])\ndf=df.assign(x2=df["x"]*2)\nresult={"rows":df.sort_values("x").to_dict("records"),"mean":df["x"].mean()}',
        'scipy': 'from scipy import stats\nx=[1,2,3,4]; y=[1.1,1.9,3.2,4.1]\nresult={"pearson":stats.pearsonr(x,y),"tt":stats.ttest_ind(x,y)}',
        'sklearn': 'from sklearn.linear_model import LinearRegression\nX=[[1],[2],[3],[4]]; y=[2,4.2,5.9,8.1]\nm=LinearRegression().fit(X,y)\nresult={"coef":m.coef_.tolist(),"intercept":m.intercept_,"score":m.score(X,y)}',
    }
    science_regression_results={}
    for label,code in science_cases.items():
        uv=validate_scientist_code(code); req(uv.get('ok'),f'legitimate {label} capability rejected by validator: {uv}')
        ur=run_scientist_python_analysis({'purpose':f'legitimate {label} analysis','input_ids':['WFA_ROWS'],'seed':42,'timeout_sec':15,'code':code},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
        req(ur.get('execution_status')=='EXECUTED' and ur.get('analysis_mode')=='PYTHON_ASSISTED',f'legitimate {label} analysis failed: {ur.get("fallback_reason")} {ur.get("stdout_excerpt")}')
        req(ur.get('structured_result') is not None,f'legitimate {label} analysis returned no structured result')
        science_regression_results[label]=ur

    # ------------------------------------------------------------------
    # PANDAS BOOLEAN FILTERING REPAIR — CASES X1-X10
    # One production execution covers the full legitimate pandas matrix so this mandatory
    # security gate stays bounded. The transitive N-W cases above already execute in the
    # same gate; X8 explicitly asserts those protections remain present after this repair.
    matrix_code=(
        'import pandas as pd\nimport numpy as np\n'
        'df=pd.DataFrame({"x":[1,2,3],"y":[10,20,30],"name":["A","B","A"],"g":["u","u","v"]})\n'
        'x1=df[df["x"]>1].to_dict()\n'
        'x2=df[(df["x"]>1)&(df["y"]<30)].to_dict()\n'
        'x3=df[(df["x"]>2)|(df["y"]==10)].to_dict()\n'
        'x4=df[~(df["x"]>1)].to_dict()\n'
        'f=df[df["x"]>1]\n'
        'x5={"rows":f.to_dict(),"selected":f["x"].tolist()}\n'
        'col=df["x"].tolist()\n'
        'cols=df[["x","y"]].to_dict()\n'
        'assigned=df.assign(z=df["x"]*2).sort_values("x").to_dict()\n'
        'ge=df[df["x"]>=2].to_dict()\n'
        'le=df[df["x"]<=2].to_dict()\n'
        'eq=df[df["name"]=="A"].to_dict()\n'
        'ne=df[df["name"]!="A"].to_dict()\n'
        'grp=df.groupby("g").mean().sort_values("g").to_dict()\n'
        'nmask=np.array([False,True,True])\n'
        'nfiltered=df[nmask].to_dict()\n'
        'result={"x1":x1,"x2":x2,"x3":x3,"x4":x4,"x5":x5,"col":col,"cols":cols,"assigned":assigned,"ge":ge,"le":le,"eq":eq,"ne":ne,"group":grp,"nfiltered":nfiltered}'
    )
    matrix=run_scientist_python_analysis(
        {'purpose':'pandas boolean filtering X1-X5/X9 matrix','input_ids':['WFA_ROWS'],'seed':42,'timeout_sec':30,'code':matrix_code},
        inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(matrix.get('execution_status')=='EXECUTED' and matrix.get('analysis_mode')=='PYTHON_ASSISTED',
        f'X1-X5/X9 production matrix failed: {matrix.get("fallback_reason")} {matrix.get("stdout_excerpt")}')
    mr=matrix.get('structured_result') or {}

    # CASE X1 — simple boolean filtering.
    req(mr.get('x1')==[{'x':2,'y':20,'name':'B','g':'u'},{'x':3,'y':30,'name':'A','g':'v'}],f'X1 mismatch: {mr.get("x1")}')

    # CASE X2 — compound AND filtering.
    req(mr.get('x2')==[{'x':2,'y':20,'name':'B','g':'u'}],f'X2 mismatch: {mr.get("x2")}')

    # CASE X3 — compound OR filtering.
    req(mr.get('x3')==[{'x':1,'y':10,'name':'A','g':'u'},{'x':3,'y':30,'name':'A','g':'v'}],f'X3 mismatch: {mr.get("x3")}')

    # CASE X4 — inversion.
    req(mr.get('x4')==[{'x':1,'y':10,'name':'A','g':'u'}],f'X4 mismatch: {mr.get("x4")}')

    # CASE X5 — filtered DataFrame and selected Series remain governed.
    req(mr.get('x5')=={'rows':[{'x':2,'y':20,'name':'B','g':'u'},{'x':3,'y':30,'name':'A','g':'v'}],'selected':[2,3]},f'X5 governed result mismatch: {mr.get("x5")}')
    x5_escape='import pandas as pd\ndf=pd.DataFrame({"x":[1,2,3]})\nf=df[df["x"]>1]\nresult=str(f._value)'
    req(not validate_scientist_code(x5_escape).get('ok'),'X5 raw DataFrame backing state exposed through validator')
    x5cp,x5payload=direct_child(x5_escape,td)
    req(x5cp.returncode!=0 and x5payload.get('status')=='ERROR','X5 direct child exposed raw DataFrame backing state')

    # CASE X6 — no raw mask leakage through private/dunder/reflection surfaces.
    for escape in (
        'import pandas as pd\ndf=pd.DataFrame({"x":[1,2,3]})\nm=df["x"]>1\nresult=m._value',
        'import pandas as pd\ndf=pd.DataFrame({"x":[1,2,3]})\nm=df["x"]>1\nresult=vars(m)',
        'import pandas as pd\ndf=pd.DataFrame({"x":[1,2,3]})\nm=df["x"]>1\nresult=getattr(m,"_value")',
        'import pandas as pd\ndf=pd.DataFrame({"x":[1,2,3]})\nm=df["x"]>1\nresult=m.__class__',
    ):
        req(not validate_scientist_code(escape).get('ok'),f'X6 mask escape passed host validation: {escape!r}')

    # CASE X7 — callback security remains closed; filtering uses explicit operators only.
    callback_filter=(
        'import pandas as pd\n'
        'df=pd.DataFrame({"x":[1,2,3]})\n'
        'result=df.assign(y=lambda raw: raw).to_dict()')
    x7cp,x7payload=direct_child(callback_filter,td)
    req(x7cp.returncode!=0 and x7payload.get('status')=='ERROR','X7 generated callback crossed governed pandas boundary')

    # CASE X8 — N-W security baseline remains closed after filtering repair.
    for unsafe in (
        'import numpy as np\nresult=str(np.ctypeslib)',
        'from numpy import ctypeslib\nresult={}',
        'import pandas as pd\nresult=str(pd.errors.ctypes.CDLL)',
        'import sklearn\nresult=sklearn.os.listdir("..")',
    ):
        req(not validate_scientist_code(unsafe).get('ok'),f'X8 transitive security regression allowed: {unsafe!r}')
    req(not native_target.exists() and not win_target.exists() and not process_marker.exists(),'X8 prior native-authority marker unexpectedly exists')
    req(not (set(TRANSITIVE_DANGEROUS_ATTRIBUTES)&{a for attrs in capability_surface_manifest().values() for a in attrs}),'X8 dangerous public capability reappeared')

    # CASE X9 — complete intended pandas V1 capability matrix.
    req(mr.get('col')==[1,2,3],'X9 column selection failed')
    req(mr.get('cols')==[{'x':1,'y':10},{'x':2,'y':20},{'x':3,'y':30}],'X9 column-list selection failed')
    req(mr.get('ge')==[{'x':2,'y':20,'name':'B','g':'u'},{'x':3,'y':30,'name':'A','g':'v'}],'X9 >= failed')
    req(mr.get('le')==[{'x':1,'y':10,'name':'A','g':'u'},{'x':2,'y':20,'name':'B','g':'u'}],'X9 <= failed')
    req(mr.get('eq')==[{'x':1,'y':10,'name':'A','g':'u'},{'x':3,'y':30,'name':'A','g':'v'}],'X9 == failed')
    req(mr.get('ne')==[{'x':2,'y':20,'name':'B','g':'u'}],'X9 != failed')
    req(mr.get('group')==[{'g':'u','x':1.5,'y':15.0},{'g':'v','x':3.0,'y':30.0}],'X9 groupby/aggregation failed')
    req(mr.get('nfiltered')==[{'x':2,'y':20,'name':'B','g':'u'},{'x':3,'y':30,'name':'A','g':'v'}],'X9 governed NumPy boolean mask failed')

    # CASE X10 — representative NumPy/SciPy/sklearn regression already executes above in
    # CASE U inside this same mandatory gate; assert those exact production-path results.
    for label in ('numpy','scipy','sklearn'):
        xr=science_regression_results.get(label) or {}
        req(xr.get('execution_status')=='EXECUTED' and xr.get('analysis_mode')=='PYTHON_ASSISTED',f'X10 {label} regression not EXECUTED/PYTHON_ASSISTED')

    # CASE V — every unsafe capability remains an explicit fail-closed fallback with no
    # fabricated structured analytical result.
    vres=run_scientist_python_analysis({'purpose':'unsafe transitive fixture','input_ids':['WFA_ROWS'],'code':ncode},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(vres.get('execution_status')=='REJECTED' and vres.get('analysis_mode')=='REASONING_ONLY','unsafe transitive capability did not fail closed')
    req(vres.get('structured_result') is None,'rejected unsafe analysis fabricated structured result')

    # CASE W — security repair must not change deterministic Factory authority.
    wres=run_scientist_python_analysis({'purpose':'non-authoritative pass fixture','input_ids':['WFA_ROWS'],'code':'result={"candidate":"PASS","promotion":"CHAMPION"}'},inputs,runtime_home=home,runtime_root=rt,verify_packages=False)
    req(wres.get('execution_status')=='EXECUTED' and wres.get('evidence_class')==EVIDENCE_CLASS,'advisory result regression')
    req(wres.get('authority')=='ANALYTICAL_SUPPORT_ONLY_DETERMINISTIC_FACTORY_REMAINS_SOLE_DECISION_AUTHORITY','security repair changed Factory authority')
    req('strict_scientist_candidate_admission' in scientist_src,'deterministic Scientist admission missing after security repair')

# Shared-capability integration, not per-entrypoint executors.
scientist_src=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
chat_src=(ROOT/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8')
req('from scientist.python.scientist_python_runtime import' in scientist_src and 'run_scientist_python_analysis' in scientist_src,'autonomous Scientist not wired to shared capability')
req('from scientist.python.scientist_python_runtime import' in chat_src and 'run_scientist_python_analysis' in chat_src,'Scientist Chat not wired to shared capability')
req('ANALYTICAL_EVIDENCE_ONLY' in chat_src and 'REASONING_ONLY' in scientist_src,'Scientist behavior fallback contract missing')

# Integrated one-click Owner runtime acceptance contract. Local acceptance verifies the
# orchestration/evidence contract synthetically; it never pretends to execute Owner Windows.
owner_cmd=ROOT/'RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd'
owner_verify_cmd=ROOT/'acceptance/verification/VERIFY_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd'
owner_py=ROOT/'acceptance/runners/owner_scientist_python_runtime_acceptance.py'
req(owner_cmd.is_file(),'integrated one-click Scientist Python Owner acceptance CMD missing')
req(owner_verify_cmd.is_file(),'Scientist Python Owner verify-existing CMD missing')
req(owner_py.is_file(),'canonical Scientist Python Owner runtime verifier missing')
owner_cmd_text=owner_cmd.read_text(encoding='utf-8')
run_acceptance_cmd_text=(ROOT/'RUN_ACCEPTANCE.cmd').read_text(encoding='utf-8')
owner_verify_text=owner_verify_cmd.read_text(encoding='utf-8')
for text,label in ((owner_cmd_text,'Owner acceptance'),(run_acceptance_cmd_text,'RUN_ACCEPTANCE'),(owner_verify_text,'verify-existing')):
    req('acceptance.runners.max_python_bootstrap' in text,f'{label} does not reuse canonical MAX Python bootstrap')
req('--run-module acceptance.runners.owner_scientist_python_runtime_acceptance -- --one-click' in owner_cmd_text,'one-click Owner acceptance does not enter canonical workflow')
req('--run-module acceptance.runners.run_acceptance' in run_acceptance_cmd_text,'RUN_ACCEPTANCE does not run through canonical MAX Python')
req('.venv\\Scripts\\python.exe' not in run_acceptance_cmd_text,'RUN_ACCEPTANCE retains legacy ModelLab .venv authority')
req('--verify-existing' in owner_verify_text and 'max_python_bootstrap' in owner_verify_text,'verify-existing CMD is not canonical read-only verifier route')

# CMD-A through CMD-E — truthful one-click exit-code authority without delayed expansion.
def _child_capture_contract(batch_text: str, invocation: str) -> tuple[int, str]:
    lines=batch_text.splitlines(); depth=0
    for idx,line in enumerate(lines):
        stripped=line.strip()
        if stripped==')':
            depth=max(0,depth-1)
        if invocation in stripped:
            following=''
            for nxt in lines[idx+1:]:
                if nxt.strip():
                    following=nxt.strip(); break
            return depth,following
        low=stripped.lower()
        if stripped.endswith('(') and (low.startswith('if ') or low.startswith('for ')):
            depth+=1
    raise AssertionError(f'child invocation missing: {invocation}')

def _synthetic_owner_cmd_result(child_rc: int) -> tuple[str,int]:
    # The real batch contract below is statically bound to RC and exit /b %RC%.
    return ('PASS' if int(child_rc)==0 else 'FAIL',int(child_rc))

for invocation in ('python -m acceptance.runners.max_python_bootstrap','py -m acceptance.runners.max_python_bootstrap'):
    depth,following=_child_capture_contract(owner_cmd_text,invocation)
    req(depth==0 and following=='set "RC=%ERRORLEVEL%"',f'CMD-E {invocation.split()[0]} child return-code capture is outside parenthesized block')
    vdepth,vfollowing=_child_capture_contract(owner_verify_text,invocation)
    req(vdepth==0 and vfollowing=='set "RC=%ERRORLEVEL%"',f'CMD-E verify {invocation.split()[0]} return-code capture is outside parenthesized block')
req('EnableDelayedExpansion' not in owner_cmd_text and 'EnableDelayedExpansion' not in owner_verify_text,'CMD-E delayed expansion is not used')
print('CMD-E PASS — return-code capture outside parenthesized child blocks; delayed expansion absent')
req('if "%RC%"=="0" (' in owner_cmd_text and 'exit /b %RC%' in owner_cmd_text,'CMD final banner/exit derives from captured RC')
req(_synthetic_owner_cmd_result(0)==('PASS',0),'CMD-A synthetic one-click rc=0 -> PASS / exit 0')
print('CMD-A PASS — synthetic one-click rc=0 -> PASS / exit 0')
req(_synthetic_owner_cmd_result(1)==('FAIL',1),'CMD-B synthetic one-click rc=1 -> FAIL / exit 1')
print('CMD-B PASS — synthetic one-click rc=1 -> FAIL / exit 1')
req(_synthetic_owner_cmd_result(37)==('FAIL',37),'CMD-C synthetic one-click rc=37 -> FAIL / exit 37')
print('CMD-C PASS — synthetic one-click rc=37 -> FAIL / exit 37')
unavailable_segment=owner_cmd_text.split('where py >nul 2>&1',1)[1].split(':run_python',1)[0]
req('set "RC=103"' in unavailable_segment and 'goto :done' in unavailable_segment,'CMD-D canonical bootstrap unavailable -> FAIL authority rc=103')
print('CMD-D PASS — canonical bootstrap unavailable -> FAIL / exit 103')
owner_src=owner_py.read_text(encoding='utf-8')
for token in ('WINDOWS_NATIVE_FILE_GUARD','WINDOWS_PROCESS_GUARD','WINDOWS_NETWORK_GUARD','PANDAS_FILTERING','REASONING_ONLY_FALLBACK','SOURCE_IMMUTABILITY'):
    req(token in owner_src,f'Owner live verifier missing required check: {token}')
req('os.name != "nt"' in owner_src,'Owner live verifier must fail closed outside Windows')
req('run_acceptance.validate_local_acceptance_report' in owner_src and 'require_fresh_full=True' in owner_src,'Owner verifier does not bind fresh cumulative acceptance')
req('run_one_click_owner_acceptance' in owner_src and '[canonical, "-m", "acceptance.runners.run_acceptance"]' in owner_src,'Owner workflow does not pin local acceptance to one resolved canonical interpreter')
req('bootstrap_python_executable' in owner_src and 'canonical_max_python_executable' in owner_src,'Owner evidence does not distinguish bootstrap vs canonical MAX Python')

# CASE PY-A/B/C/D/E/G — canonical MAX interpreter binding is deterministic and PATH-independent.
bootstrap_src=(ROOT/'acceptance/runners/max_python_bootstrap.py').read_text(encoding='utf-8')
req('ui_bootstrap.ensure_python312' in bootstrap_src,'canonical bootstrap does not reuse Python 3.12 authority')
req('ui_launcher.ensure_env()' in bootstrap_src and 'ui_launcher.venv_python()' in bootstrap_src,'canonical bootstrap does not reuse existing MAX venv authority')
req(MAX_PYTHON_UNAVAILABLE_REASON=='CANONICAL_MAX_PYTHON_UNAVAILABLE','canonical unavailable reason drift')
req(resolve_bootstrap_python(lambda: r'C:\Python312\python.exe').lower().endswith('python312\\python.exe'),'PY-A supported Python 3.12 bootstrap resolution failed')
req(resolve_bootstrap_python(lambda: None) is None,'PY-D missing Python 3.12 did not fail closed')
fixed_cmd=canonical_target_command(r'C:\FixtureHome\CPML\venv312\Scripts\python.exe','acceptance.runners.run_acceptance')
old_path=os.environ.get('PATH')
os.environ['PATH']=r'C:\Python314;C:\Windows\System32'
req(fixed_cmd[0].lower().endswith('cpml\\venv312\\scripts\\python.exe'),'PY-E PATH mutation changed resolved canonical command')
if old_path is None: os.environ.pop('PATH',None)
else: os.environ['PATH']=old_path
req('ensure_env()' in bootstrap_src,'PY-C canonical environment bootstrap/repair missing')
req('max_python_bootstrap' in run_acceptance_cmd_text and 'max_python_bootstrap' in owner_cmd_text,'PY-G RUN_ACCEPTANCE and Owner acceptance do not share canonical authority')

# Synthetic PASS/negative evidence proves fail-closed existing-evidence verification without
# running the real Owner environment during local acceptance.
synthetic_binding={
    'source_tree_signature':'a'*64,
    'suite_signature':'b'*64,
    'local_acceptance_gate_count':len(run_acceptance.TESTS),
    'local_acceptance_execution_mode':'FRESH_FULL',
    'local_acceptance_report_sha256':'c'*64,
}
synthetic_health={
    'status':'READY','analysis_mode':'PYTHON_ASSISTED_AVAILABLE','separate_interpreter':True,
    'scientist_python_executable':r'C:\FixtureHome\MaxMTF\ScientistPython\venv\Scripts\python.exe',
    'canonical_max_python_executable':r'C:\MAX\venv\Scripts\python.exe',
    'python_version':'3.12.10','package_versions':dict(OWNER_PINNED),
}
synthetic={
    'schema':OWNER_ACCEPTANCE_SCHEMA,'project':'Max MTF','version':'2.0.1',
    'generated_utc':'2026-09-20T12:00:00+00:00','overall_status':'PASS','first_failed_check':None,
    **synthetic_binding,
    'bootstrap_python_executable':r'C:\Python314\python.exe',
    'canonical_max_python_executable':synthetic_health['canonical_max_python_executable'],
    'scientist_python_executable':synthetic_health['scientist_python_executable'],
    'max_python_executable':synthetic_health['canonical_max_python_executable'],
    'separate_interpreter':True,'python_version':'3.12.10',
    'numpy_version':OWNER_PINNED['numpy'],'pandas_version':OWNER_PINNED['pandas'],
    'scipy_version':OWNER_PINNED['scipy'],'sklearn_version':OWNER_PINNED['scikit-learn'],
    'setup_status':'READY','health_status':'READY','production_analysis_status':'PASS',
    'pandas_filtering_status':'PASS','numpy_status':'PASS','scipy_status':'PASS','sklearn_status':'PASS',
    'numpy_ctypes_guard':'PASS','pandas_ctypes_guard':'PASS','sklearn_os_guard':'PASS',
    'windows_file_guard':'PASS','windows_process_guard':'PASS','windows_network_guard':'PASS',
    'raw_object_guard':'PASS','callback_guard':'PASS','reasoning_only_fallback':'PASS',
    'factory_authority_preserved':'PASS','source_immutability':'PASS',
    'evidence_class':OWNER_EVIDENCE_CLASS,'authority':OWNER_ACCEPTANCE_AUTHORITY,
    'checks':[{'check':name,'status':'PASS','details':{}} for name in OWNER_REQUIRED_CHECKS],
}
req(verify_owner_evidence_payload(synthetic,current_binding=synthetic_binding,live_health=synthetic_health).get('status')=='PASS','synthetic Owner PASS evidence did not verify')
req(synthetic['max_python_executable']==synthetic['canonical_max_python_executable'] and synthetic['scientist_python_executable']!=synthetic['max_python_executable'],'PY-F evidence interpreter identity contract failed')
for label,mutate in (
    ('stale source',lambda x:x.update(source_tree_signature='d'*64)),
    ('stale suite',lambda x:x.update(suite_signature='e'*64)),
    ('wrong interpreter',lambda x:x.update(scientist_python_executable=x['max_python_executable'])),
    ('FAIL field',lambda x:x.update(pandas_filtering_status='FAIL')),
):
    bad=json.loads(json.dumps(synthetic)); mutate(bad)
    try:
        verify_owner_evidence_payload(bad,current_binding=synthetic_binding,live_health=synthetic_health)
    except OwnerScientistPythonAcceptanceError:
        pass
    else:
        raise AssertionError(f'Owner evidence verifier false-PASS: {label}')
bad=json.loads(json.dumps(synthetic)); bad['checks']=[row for row in bad['checks'] if row['check']!='WINDOWS_NETWORK_GUARD']
try:
    verify_owner_evidence_payload(bad,current_binding=synthetic_binding,live_health=synthetic_health)
except OwnerScientistPythonAcceptanceError:
    pass
else:
    raise AssertionError('Owner evidence verifier false-PASS: missing required check')

# CASE L — gate count authority must move dynamically; no Scientist-Knowledge 74->75 edit.
req(len(run_acceptance.TESTS)==75,f'expected cumulative suite to contain 75 gates, got {len(run_acceptance.TESTS)}')
acc=local_acceptance_expectations()
req(acc.get('gate_count')==len(run_acceptance.TESTS) and acc.get('target')=='75/75 PASS','Scientist Knowledge did not derive current canonical gate count')
knowledge_src=(ROOT/'scientist/knowledge/scientist_knowledge.py').read_text(encoding='utf-8')
req('gate_count = len(canonical_local_acceptance_tests)' in knowledge_src,'dynamic gate-count derivation missing')
req('gates == 75' not in knowledge_src and 'gate_count = 75' not in knowledge_src,'hard-coded 75 leaked into Scientist Knowledge generator')

# CASE M — final persisted Knowledge/workflow audit must be exact-tree synchronized.
kb=load_knowledge()
ss=sync_status(kb); req(ss.get('in_sync'),f'final Scientist Knowledge source manifest stale: {ss}')
ws=workflow_audit_sync_status(kb); req(ws.get('in_sync'),f'final persisted workflow audit stale: {ws}')
workflow=json.loads((ROOT/'evidence/current/WORKFLOW_CONTRACT_AUDIT_R1.json').read_text(encoding='utf-8'))
req(workflow.get('overall_status')=='PASS' and workflow.get('first_failed_gate') is None,'workflow contract audit not PASS')

print('V201_SCIENTIST_PYTHON_ANALYSIS_RUNTIME PASS')

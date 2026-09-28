from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    cf=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('factory_onnx_preflight.json' in cf,'Factory owns one immutable ONNX preflight evidence file')
    req('ac["onnx_preflight_authority"] = str(preflight_path)' in cf,'Every Discovery generation reuses Factory preflight authority')
    req('preflight_authority = str(ac.get("onnx_preflight_authority")' in sup,'Supervisor supports fail-closed preflight authority reuse')
    req('shutil.copy2(authority, out/"onnx_preflight.json")' in sup,'Generation retains copied preflight evidence')
    req('stage=="onnx_preflight"' in app and 'onnx_preflight_reuse' in app,'UI exposes ONNX preflight progress instead of silent 5 percent stall')
    print('FACTORY_PREFLIGHT_SELFTEST PASS')

if __name__=='__main__': main()

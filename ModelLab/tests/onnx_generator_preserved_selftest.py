from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def main():
    ox=(ROOT/'models/onnx_export.py').read_text(encoding='utf-8')
    cf=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req(all(x in ox for x in ('def export_tabular','def export_hybrid','def verify_hybrid_onnx','def preflight_export_stack')),'ONNX generator/export/parity functions preserved')
    req('preflight_export_stack' in cf and 'factory_onnx_preflight.json' in cf,'Factory keeps one-time ONNX preflight')
    req('champion_runtime' in cf and 'export_hybrid' in cf and 'export_tabular' in cf,'Forward winner generates Champion ONNX runtime artifact')
    req('FACTORY_WINNER_RUNTIME_BLOCKED' in cf,'ONNX parity/export fails closed after Champion selection')
    print('ONNX_GENERATOR_PRESERVED PASS')
if __name__=='__main__': main()

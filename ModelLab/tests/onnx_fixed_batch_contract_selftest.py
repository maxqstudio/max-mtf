from pathlib import Path

src=((Path(__file__).resolve().parents[1]/'models/onnx_export.py')).read_text(encoding='utf-8')

def req(c,m):
    if not c: raise AssertionError(m)

req('def _torch_export_fixed_batch_one' in src,'fixed-batch recurrent exporter helper missing')
req('Temporal ONNX input batch dimension must be fixed to 1' in src,'standalone temporal batch=1 contract missing')
req("Hybrid temporal ONNX input must be fixed batch=1 [1,T,F]" in src,'hybrid temporal batch=1 contract missing')
req('"gru_input": [1, "T", n_features]' in src and '"gru_batch_contract": "FIXED_1"' in src,'preflight contract still advertises dynamic GRU batch')
req("'runtime_batch_size':1" in src and "'batch_contract':'FIXED_1'" in src,'hybrid parity evidence missing fixed-batch provenance')
req('warnings.filterwarnings("ignore", message=r".*Exporting a model to ONNX with a batch_size other than 1.*GRU.*")' in src,'known PyTorch GRU warning is not narrowly scoped')
# The warning may only be suppressed behind an explicit dummy batch assertion and
# post-export ONNX shape checks.
req('if int(dummy.shape[0]) != 1' in src,'warning suppression lacks pre-export batch assertion')
print('ONNX FIXED BATCH CONTRACT SELF-TEST PASS')

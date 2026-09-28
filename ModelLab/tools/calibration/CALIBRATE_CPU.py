from core.project_paths import MODELLAB_ROOT
from pathlib import Path
import json
from host.cpu_resource import calibrate_cpu_profile
ROOT=MODELLAB_ROOT
out=ROOT/'config/cpu_calibration.json'
prof=calibrate_cpu_profile(out)
print(json.dumps(prof,indent=2))
print(f'\nSaved: {out}')

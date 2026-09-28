from host.hardware_profile import collect_hardware_profile, summarize_hardware_profile
from research.research_architect import capability_catalog
from host.resource_preflight import compile_resource_capacity


def req(c,m):
    if not c: raise AssertionError(m)

# Synthetic regression for the exact Owner evidence defect: logical=12 with unknown
# physical topology must never be relabelled as physical=12.
profile={
    'profile_hash':'synthetic',
    'memory':{'total_gib':None,'available_gib':None,'source':'UNAVAILABLE'},
    'nvidia':{'devices':[]},
    'torch':{'cuda_available':False},
    'cpu':{'physical_cores':None,'logical_threads':12,'planning_cores':6,'core_count_source':'CONSERVATIVE_LOGICAL_ESTIMATE'},
}
cat=capability_catalog(profile,{'research_architecture':{'family_selection_mode':'AUTO'}})
hw=cat['hardware']
req(hw['physical_cores'] is None,'logical SMT threads were falsely exposed as physical cores')
req(hw['logical_threads']==12 and hw['planning_cores']==6,'planning core semantics lost')
req(hw['ram_gib'] is None,'unknown RAM must remain unknown, not 0.0 authority')
rc=compile_resource_capacity(profile,{'safe_ram_fraction':0.75,'safe_vram_fraction':0.8,'max_single_experiment_minutes':120},{}, {})
rhw=rc['hardware']
req(rhw['physical_cores'] is None and rhw['planning_cores']==6,'resource preflight core semantics incorrect')
req(rc['limits']['ram_gib'] is None,'unknown RAM must not fabricate a 0 GiB hard limit')

# Actual build-host probe: if physical topology/RAM is available it must be internally sane.
actual=collect_hardware_profile(); summ=summarize_hardware_profile(actual)
logical=int(summ.get('logical_threads') or 1); planning=int(summ.get('planning_cores') or 1)
req(1 <= planning <= logical,'planning cores outside logical topology')
if summ.get('physical_cores') is not None:
    req(1 <= int(summ['physical_cores']) <= logical,'physical cores outside logical topology')
if summ.get('ram_total_gib') is not None:
    req(float(summ['ram_total_gib']) > 0,'detected RAM must be positive')
print('HARDWARE PROFILE TRUTH SELF-TEST PASS')

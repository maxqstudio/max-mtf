from __future__ import annotations
import json
import tempfile
from pathlib import Path

from models.model_lab import sha256_file
from factory.supervisor_agent import _research_authority
from data.feature_label_audit import _expected_research_hash


def require(cond, msg, checks):
    if not cond:
        raise AssertionError(msg)
    checks.append(msg)
    print('PASS', msg)


def main():
    checks=[]
    with tempfile.TemporaryDirectory() as td:
        runs=Path(td)/'runs'; runs.mkdir()
        agent=runs/'AGENT_SOURCE'; policy=runs/'POLICY_SOURCE'; fresh=runs/'FRESH_LEGACY'
        for d in (agent,policy,fresh): d.mkdir()
        snap=agent/'source_window.csv'; snap.write_text('signal_time;x\n2025.02.28 23:00;1\n',encoding='utf-8')
        research_hash=sha256_file(snap)
        master=Path(td)/'master.csv'; master.write_text('signal_time;x\n2025.02.28 23:00;1\n2026.09.09 08:00;2\n',encoding='utf-8')
        fresh_hash=sha256_file(master)
        agent_manifest={
            'run_id':'AGENT_SOURCE','run_type':'SUPERVISOR_AGENT','status':'REJECTED',
            'source_csv_sha256':research_hash,'source_raw_end':'2025-02-28 23:00:00',
            'research_window':{'authority_snapshot_sha256':research_hash,'source_raw_end':'2025-02-28 23:00:00','research_from':'2025-01-01','research_to':'2025-02-28'},
        }
        policy_manifest={
            'run_id':'POLICY_SOURCE','run_type':'POST_LOCKED_POLICY_DISCOVERY','status':'POLICY_CV_PASS_NEEDS_FRESH_HOLDOUT',
            'source_run_id':'AGENT_SOURCE','source_csv_sha256':research_hash,'source_raw_end':'2025-02-28 23:00:00',
        }
        # Exact v0.6.6 defect shape: mutable fresh hash overwrote source_csv_sha256.
        fresh_legacy={
            'run_id':'FRESH_LEGACY','run_type':'FRESH_HOLDOUT_VALIDATION','status':'REJECTED',
            'source_run_id':'AGENT_SOURCE','policy_run_id':'POLICY_SOURCE','source_csv_sha256':fresh_hash,
        }
        for d,m in ((agent,agent_manifest),(policy,policy_manifest),(fresh,fresh_legacy)):
            (d/'model_manifest.json').write_text(json.dumps(m,indent=2),encoding='utf-8')

        auth=_research_authority(agent_manifest)
        require(auth['sha256']==research_hash,'research authority hash resolves immutable snapshot',checks)
        require(auth['cutoff']=='2025-02-28 23:00:00','research authority cutoff is snapshot end, not training-memory split',checks)
        recovered=_expected_research_hash(fresh,fresh_legacy,runs)
        require(recovered==research_hash,'legacy v0.6.6 fresh lineage recovers immutable research hash from ancestry',checks)
        require(recovered!=fresh_hash,'fresh/master hash is never accepted as research source hash',checks)

        sup=(Path(__file__).resolve().parents[1]/'factory/supervisor_agent.py').read_text(encoding='utf-8')
        require('"fresh_input_csv_sha256":updated_hash' in sup or '"fresh_input_csv_sha256": updated_hash' in sup,
                'fresh input hash has dedicated manifest field',checks)
        require('"research_source_csv_sha256":research_hash' in sup or '"research_source_csv_sha256": research_hash' in sup,
                'fresh manifests preserve immutable research hash',checks)
        app=(Path(__file__).resolve().parents[1]/'ui/app.py').read_text(encoding='utf-8')
        require('authority_research_meta' in app and 'fresh strictly >' in app,
                'UI displays lineage-resolved research cutoff for fresh validation',checks)

    out=Path(__file__).resolve().parents[1]/'evidence/history/LINEAGE_HASH_ACCEPTANCE_v0_6_7.json'
    out.write_text(json.dumps({'version':'0.6.9','status':'PASS','checks':checks},indent=2),encoding='utf-8')
    print('LINEAGE HASH ACCEPTANCE PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

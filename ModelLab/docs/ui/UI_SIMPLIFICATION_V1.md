# Operator UI Contract — v0.7.3 R5

Top-level route: `Data → Discovery → Pool → CPCV → Tournament → Monte Carlo → Forward Championship → Champion`; Advanced remains configuration/audit.

Discovery contains WFA/OOF research intelligence, Policy Discovery, Feature+Label Audit, Guided Research, Scientist and Research Memory. CPCV is now an explicit finalist stage and is no longer hidden inside Discovery generations.

Scientist Chat remains removed. Scientist/Director output appears as automatic research reports. Master Orchestrator is the primary action; manual stage actions remain available for repair/audit.

## R5 operator information architecture

`Research` is the only normal lifecycle control page and refreshes live status every 2 seconds. Stage pages are live detailed inspectors: CPCV, for example, lists every Pool finalist and its WAITING/RUNNING/PASS/FAIL state, live split count, committed split metrics, failure topology, and Scientist reports. Stage pages do not start duplicate workers.

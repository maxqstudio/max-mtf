# Max Research Agent — v0.7.5 R6 UI Component Chat R4 Hotfix6

## Scope
Bounded UI repair only. Scientific/research authority remains v0.7.5 R6.

## Owner visual evidence
During START RESEARCH the lifecycle loading row was rendered below the fixed bottom button. On short/normal-height layouts this could be clipped by the viewport while a large empty nav region remained above the footer. Once a worker became active, PAUSE/STOP appeared but startup/preflight activity feedback largely disappeared.

## Repair
- START pending loader now renders **above** the disabled `STARTING…` button.
- Active research now keeps a compact animated lifecycle row **above** `PAUSE | STOP`, sourced from the active job's committed `last_event.stage/message`.
- STOPPING state reuses that same upper activity slot instead of adding a second row below the buttons.
- Left lifecycle footer is allowed to size to content and no longer clips its busy row.
- Busy row wraps safely on narrow left-panel widths.

## Contract
Left footer ordering is now:

```
Lifecycle activity / loading
Lifecycle button row
```

The navigation region remains the only flexible/scrolling region above the fixed lifecycle footer.

## Verification
- `python -m py_compile app.py` PASS
- `python lifecycle_loader_layout_selftest.py` PASS
- `python ui_event_state_selftest.py` PASS
- `python responsive_shell_selftest.py` PASS
- Research-core preservation: 21/21 byte-identical to Hotfix5.

Real Windows visual acceptance remains Owner-authoritative.

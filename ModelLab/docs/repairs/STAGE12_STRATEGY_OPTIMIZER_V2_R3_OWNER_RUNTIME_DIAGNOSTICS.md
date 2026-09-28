# Stage 12 Strategy Optimizer V2 R3 - Owner Runtime Diagnostics

Status: LOCAL REPAIR CANDIDATE. Owner MT5 runtime remains external.

## Owner defect evidence

Owner runtime reached `FAILED` during MetaEditor compile. The V2 UI only displayed `MetaEditor compile failed; inspect metaeditor_compile.log`, forcing the operator to locate an internal run log. The same screen used the ambiguous label `Confirm Symbol`, and the package flow did not state clearly that the EA is auto-deployed by the controller.

## Contract repair

1. **No manual EA copy.** `START MT5 OPTIMIZATION` copies the exact packaged `EA_v1_06/Max.mq5` into the selected MT5 data directory under `MQL5/Experts/MaxResearch/`, deletes any stale EX5, and invokes MetaEditor against that exact source.
2. **Automatic evidence.** Every run owns `owner_acceptance/evidence/strategy_optimizer/<job_id>/`. Request/status, worker stdout/stderr, exact packaged MQ5 source, MetaEditor command/log/context, round set/ini/XML files, and champion artifacts are published there automatically.
3. **Automatic failure diagnostic.** Any worker failure creates `historical external: diagnostic.json`, `diagnostic.txt`, and a single `<job_id>_diagnostic.zip`. The UI displays the parsed error excerpt, the evidence path, an `OPEN EVIDENCE FOLDER` action on Windows, and a `DOWNLOAD DIAGNOSTIC ZIP` action.
4. **Relative Value naming.** The UI label is `Relative reference symbol`, not `Confirm Symbol`. It is required because the seventh strategy family computes correlation/divergence between Main Symbol normalized returns and the reference symbol. It is not an entry-confirmation toggle.
5. **Seven-family authority unchanged.** Main Symbol and Relative reference symbol must be distinct and available to MT5, and all seven family weights remain > 0.
6. **KPI unchanged.** Optimizer eligibility remains `PF >= 1.00`, `RF >= 0.00`, `Expectancy R >= 0.00`, `trades > 0`.

## Failure handling

The operator must not be told to hunt internal files as the primary diagnostic path. On failure, evidence is already collected and surfaced in the UI. If external review is needed, the one-file diagnostic ZIP is the handoff artifact.

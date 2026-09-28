# REPAIR v0.8.1 — Strategy Optimizer atomic resume

- Durable per-round checkpoint before MT5 launch and after completion.
- `WAITING_FOR_REPORT` is recoverable; resume never reruns the same MT5 round.
- Report discovery uses SpreadsheetML internal identity, not filename/path assumptions.
- Scans `MQL5/Profiles/Tester` and copies matched XML into immutable run evidence.
- Bounded legacy v0.8.0 Round-1 recovery from compatible `historical external: ReportOptimizer-*.xml`.
- Owner-selectable optimization parameter universe; frozen inputs stay `N`.
- Scientist may refine only Owner-selected inputs.

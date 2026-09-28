# Max MTF v2.0.0 — Foundation Contract

## Project boundary

Max MTF is a separate project forked from the exact Max single-timeframe v1.4.5 codebase. The single-timeframe project is closed at v1.4.5 except bug fixes. Max MTF owns its own runtime, governance, challengers, champions, releases, and MT5 namespace.

## Initial state

- Project: **Max MTF**
- Project version: **2.0.0**
- EA version: **2.00**
- Active EA: `EA_v2_00/baseline/Max_MTF.mq5`
- Strategy Champion: **null / 0**
- Model Champion: **null / 0**
- Active release: `BASELINE-MTF-V2`
- Baseline is **not** a Champion.
- Existing single-TF strategy parameter defaults are inherited exactly as the seed strategy baseline; MTF behavior is not claimed until its dedicated implementation phases pass acceptance.

## MTF role contract

- `TF+2`: Trend / Regime / Volatility
- `TF+1`: Setup / Pullback / Breakout / Structure
- `TF`: Primary `SELL / SKIP / BUY` decision
- `TF-1`: Entry Timing / Execution

Reference mapping: H4 / H1 / M15 / M5.

## Artifact layout

- `EA_v2_00/baseline/` — current canonical EA copy.
- `EA_v2_00/challengers/` — immutable Strategy Challenger bundles.
- `EA_v2_00/archive/` — prior baseline/Champion EA archives.
- `Models/baseline/` — canonical promoted model copy; empty at bootstrap.
- `Models/challengers/` — immutable Model Challenger bundles.
- `Models/archive/` — prior promoted model archives.
- `Releases/active/` — current atomic EA/model release identity.
- `Releases/challengers/` — release candidates.
- `Releases/archive/` — prior releases.

## Promotion invariants

1. Optimizer winner creates a Strategy Challenger; it never auto-replaces baseline/Champion.
2. First Strategy promotion archives the seed baseline, then makes the selected Challenger Strategy Champion #1.
3. Later Strategy promotion demotes/archives prior promoted authority with provenance.
4. Model Challenger always retains the exact EA/strategy authority snapshot under which it was researched.
5. Future unified Model promotion is an atomic release transaction: archive old active release, replace canonical EA/model copies, compile/verify, deploy into the verified MT5 terminal data root, then commit registry state.
6. Failure before commit must rollback canonical project artifacts and terminal deployment.

## MT5 deployment authority

Never deploy to raw `C:\`.

Target must be a verified MT5 terminal **data root**, normally:

`C:\Users\<user>\AppData\Roaming\MetaQuotes\Terminal\<TERMINAL_ID>\`

Canonical Max MTF targets under that root:

- `MQL5\Experts\MaxMTF\Max_MTF.mq5/.ex5`
- `MQL5\Files\models\MaxMTF\...`
- `MQL5\Profiles\Tester\Max_MTF.set`

A path is eligible only if it already identifies an MT5 terminal data root containing `MQL5`. Raw drive roots fail closed.

## Namespace isolation

Max MTF must not collide with Max v1.4.5 runtime artifacts. Canonical names use the `Max_MTF` namespace, including training, telemetry, trade audit, optimizer metrics, report, and Tester preset files.

## Phase-0 limitation

This foundation phase does **not** claim MTF trading logic is implemented. It creates the separate project identity, zero-Champion bootstrap, active EA v2.00 baseline, isolated artifact layout, terminal-root authority, and lifecycle foundation required before MTF data/strategy/model implementation begins.

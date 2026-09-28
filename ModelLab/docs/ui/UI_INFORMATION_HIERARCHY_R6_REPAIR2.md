# CPMF v0.7.5 R6 Repair2 — UI Information Hierarchy

## Scope

UI-only repair. Research/backend authority is intentionally unchanged. The running Factory/worker is not restarted or migrated by this package.

## Design contract

The cockpit now uses **balanced modular grouping** rather than either extreme:

- no card for every metric/field;
- no single mega-card containing an entire page;
- one bordered card for a major conceptual group;
- subsection headings/dividers for related controls inside that group;
- full-width data tables for dense evidence;
- progressive disclosure only for secondary tuning, event logs, forensics, journals, pricing, and legacy diagnostics;
- important live research state remains visible without opening a disclosure.

Density is contextual:

- **comfortable** — configuration, API credentials, research windows, model controls;
- **compact** — live status and summary metrics;
- **dense** — candidate/evidence tables and forensic data.

## Major page structure

### Research

1. Active research cycle
2. Live candidates
3. Latest committed Scientist analysis
4. Previous cycle is secondary disclosure

### Data

1. Dataset identity
2. Research windows + chronology + sample preview
3. Compute route is secondary disclosure

### Discovery

1. Dataset identity
2. Discovery plan
3. Research progress
4. Live candidate leaderboard
5. LLM usage / latest Scientist report
6. Historical/forensic details remain available

### Pool / CPCV / Tournament / Monte Carlo / Forward / Champion

Each page uses a visible stage summary and a separate dense evidence/results region where applicable. Forensics remain available but collapsed by default.

### Advanced

Visible major groups:

1. Scientist connection
2. Model routing / active stack
3. Adaptive model research
4. Compute & hardware
5. Validation & research authority

Secondary tuning remains available through disclosure:

- Supervisor & Scientist creativity
- detailed Risk KPI thresholds
- Champion Factory settings
- Research authority / legacy settings
- Legacy diagnostics
- token pricing

## Information-preservation rule

The UI repair does not remove scientific/operator information. It changes only presentation priority:

- **always visible:** active state, core dataset identity, research limits, pool authority, current stage, key PASS/FAIL counts, active model route, model/hardware authority summaries;
- **table/list:** candidate and validation evidence;
- **collapsed secondary detail:** event logs, historical journals, pricing, forensic breakdowns, rarely edited advanced thresholds.

## API connection repair

The CONNECT action now has a bounded proportional width and lives with Credentials instead of appearing as an oversized/undersized unrelated asset. Provider/endpoint and credentials are vertically separated as subsections.

## Backend invariants

No intended change to:

- Factory process lifecycle;
- START/PAUSE/STOP/RESUME/ABORT authority;
- research plan freezing;
- deterministic Discovery;
- Scientist/Director logic;
- candidate generation/admission;
- capacity/resource preflight;
- WFA/CPCV/Tournament/Monte Carlo/Forward logic;
- model training/export/parity logic;
- config defaults or persistence contracts.

The runtime source repair is confined to `ModelLab/ui/app.py`; added documentation/selftest files are non-backend evidence.

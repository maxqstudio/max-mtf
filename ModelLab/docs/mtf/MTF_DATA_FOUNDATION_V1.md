# Max MTF v2.0.1 — MTF-1 Canonical Data Foundation

## Scope

MTF-1 establishes the causal market-data authority for Max MTF. It does **not** enable MTF strategy execution or MTF model training yet.

Reference ladder:

- `TF+2 = H4` — context / regime / trend / volatility
- `TF+1 = H1` — setup / pullback / breakout / structure
- `TF = M15` — primary decision clock
- `TF-1 = M5` — entry-timing / execution clock

## Value authority

**M5 is the only canonical OHLCV value authority.**

Native MT5 M15/H1/H4 bars are fetched only for:

1. exact broker-native bar boundaries; and
2. deterministic parity verification.

Canonical M15/H1/H4 OHLCV is rebuilt from M5. A native higher-timeframe OHLCV mismatch fails closed; native H1/H4 values are never silently copied into the canonical views.

This avoids guessing broker H4 boundaries, weekend/session gaps, or DST shifts from wall-clock rules.

## Clock contract

- Canonical stored clock: timezone-aware `UTC`.
- MT5/POSIX epoch seconds are interpreted as UTC.
- Imported timezone-aware timestamps are converted to UTC.
- Imported timezone-naive timestamps require an explicit source timezone.
- DST-ambiguous or nonexistent local timestamps fail closed; Max never guesses a fold/offset.
- `open_time_utc` is bar open.
- `close_time_utc` is the next native boundary for M15/H1/H4.
- M5 close is `open + 5 minutes`.

## Closed-bar alignment

For an M15 decision at time `t`:

- H4 = latest fully closed H4 with `close_time_utc <= t`;
- H1 = latest fully closed H1 with `close_time_utc <= t`;
- M15 = the primary bar closing exactly at `t`;
- M5 = latest fully closed M5 with `close_time_utc <= t`.

M5 bars with `close_time_utc > t` are forbidden from directional context for the decision at `t`.

The alignment output stores timestamps/lineage only in MTF-1. Role-specific features are introduced in MTF-2.

## Missing-bar authority

Max must **not** infer missing M5 bars from naive 5-minute wall-clock continuity because broker sessions contain legitimate weekends/closures.

For imported M5 sources, continuity authority is the exact native M5 timestamp set from the same verified MT5 terminal/feed/window:

`source M5 timestamps == native broker M5 timestamps`

Missing or extra timestamps fail closed. For `IMPORTED_M5`, this proof is mandatory at seal time: the sealer requires the native M5 reference, recomputes the exact reference audit, verifies its identity-bound evidence/hash, and rejects the bundle if the proof is absent or stale. Higher-TF aggregate parity cannot substitute for this gate, including when a missing M5 bar is aggregate-neutral. Direct MT5 collection is itself the native source authority for the sealed collection window.

No market bar is forward-filled or synthesized.

## Deterministic resampling parity

For every fully closed native M15/H1/H4 interval:

- Open = first M5 open
- High = maximum M5 high
- Low = minimum M5 low
- Close = last M5 close
- Tick volume = sum of M5 tick volume
- Real volume = sum of M5 real volume

The reconstructed result must match the native MT5 higher-timeframe reference. Tick volume is exact. Real volume is exact whenever either source/reference has populated real volume; zero-only MT5 real volume is explicitly recorded as unavailable. Failure blocks the bundle.

## Lineage

Every sealed bundle includes hashes for:

- canonical M5 view;
- canonical M15 view;
- canonical H1 view;
- canonical H4 view;
- causal alignment index;
- broker/source identity;
- resampling-parity evidence.

The combined manifest gets one `bundle_identity_sha256`. Before commit, all frame/alignment hashes and bundle identity are recomputed against the actual data. A sealed destination cannot be overwritten. Commit uses a verified staging directory followed by an atomic rename; Data Quality evidence is identity-bound in the manifest before sealing.

Canonical project directories:

- `Data/MTF/native/`
- `Data/MTF/bundles/`

## Research activation boundary

`mtf_data.enabled_for_research = false` in MTF-1.

This is deliberate. The inherited v1.4.5 research engine remains scientifically unchanged until MTF-2/3 define role-specific features, labels, dependency horizons, and timestamp-based purge/embargo authority.

## Source/contract acceptance

MTF-1 source acceptance must prove:

- exact H4/H1/M15/M5 ladder/config;
- deterministic M5-derived M15/H1/H4 parity;
- causal as-of alignment at shared boundaries;
- future-M5 adversarial injection cannot affect an earlier M15 decision;
- exact native-M5 missing timestamp detection;
- legitimate broker/session gaps are not falsely treated as missing wall-clock bars;
- timezone-naive input fails without explicit timezone;
- DST ambiguity fails closed;
- higher-TF native values cannot become canonical value authority;
- all four frame hashes + alignment hash are persisted;
- real-volume mismatch fails when available and unavailable zero-only state is explicit;
- stale manifest/data binding is rejected;
- sealed bundle overwrite is rejected;
- staging verification failure leaves no final bundle;
- active-release records resolve to the current canonical EA using portable path + exact SHA + EA-version parity;
- imported M5 sealing requires exact native-M5 continuity proof recomputed at seal time;
- packaged runtime Strategy Registry uses portable baseline identity;
- cumulative acceptance cannot mutate packaged runtime authority.

## External Owner-machine acceptance

Source acceptance cannot prove the Owner broker runtime. MTF-1 remains externally pending until a real Owner MT5 sample demonstrates:

1. direct M5 collection from the verified terminal/feed;
2. M5-derived M15/H1/H4 OHLCV parity against native MT5 bars;
3. exact symbol/server/terminal data-path provenance;
4. zero causal-alignment violation on the sealed sample.

This external runtime evidence is required before MTF-1 can be considered production-runtime frozen.

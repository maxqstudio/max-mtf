# CPMF v0.7.0 R4 — CSV Delimiter Authority Repair

- Fixed Champion Factory Discovery/Tournament/Fresh readers that used pandas comma defaults against MT5 semicolon CSV authorities.
- Added `read_csv_auto()` as the shared CSV boundary reader for semicolon MT5 master/snapshots and comma internal evidence CSVs.
- Repaired Scientist read-only dataset summary and run identity to use the same boundary reader.
- Added `CSV_DELIMITER_AUTHORITY` acceptance reproducing the exact `usecols` failure on semicolon source and verifying snapshot identity.
- No settings/API reset; `%LOCALAPPDATA%\ComplexPolicy\ModelLab` remains the persistent authority.

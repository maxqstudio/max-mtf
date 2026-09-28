# Settings Persistence V1 · CPMF v0.6.8

## Stable location

On Windows, user settings live outside the versioned package folder:

`%LOCALAPPDATA%\ComplexPolicy\ModelLab\`

This prevents settings from disappearing when `CPMF_v0_6_8` is replaced by a later revision.

Files:

- `historical external: settings.json` — versioned non-secret config + serializable operator/UI state;
- `historical external: settings.backup.json` — previous valid settings snapshot;
- `llm_api_key.dpapi` — API secret encrypted with Windows DPAPI for the current Windows user.

## Behavior

- every normal Streamlit rerun atomically persists current settings;
- startup restores saved config and operator/widget selections before rendering controls;
- corrupt primary settings fall back to the backup rather than silently reset to defaults;
- provider, model, endpoint, research settings, model toggles, budgets, and relevant UI selections persist;
- API keys are never written to JSON/plaintext by the settings store.

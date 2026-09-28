# CPMF v0.7.4 R2 Hotfix3 — UI State Persistence Hardening

## Defects repaired
- Streamlit action-widget state could be persisted/restored and crash widget creation (`StreamlitValueAssignmentNotAllowedError`).
- The old blacklist persistence policy was fragile: a newly introduced button key could regress without being added to the blacklist.
- Sensitive UI fields such as `llm_api_key_input` could be captured by generic UI-state persistence even though the canonical API key is protected separately with DPAPI.
- Legacy settings could retain stale event/sensitive UI keys.
- Several acceptance tests still asserted pre-cockpit button labels instead of the current compact sidebar lifecycle UI.

## Authority after Hotfix3
- UI state persistence is allowlist-only. Unknown/new widget keys are transient by default.
- All Streamlit button/action keys are non-persistable.
- Keys containing api_key/apikey/secret/password/token/credential are non-persistable.
- Legacy settings are scrubbed automatically on load and the primary settings file is self-healed.
- DPAPI secret storage remains the only persistent API-key authority.
- Hotfix1 Windows-safe ONNX artifact naming is preserved.
- R2 adaptive family/compute control is preserved.

## Acceptance
- Full cumulative acceptance: 50/50 PASS
- first_failed_gate: null
- UI button AST audit: all explicit button keys non-persistable
- legacy plaintext-like UI secret scrub test: PASS

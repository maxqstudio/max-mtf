# MAX Research Agent v0.11.2 — Research Director JSON Recovery

## Runtime defect
A provider-successful Factory `GENERATION_REVIEW` could return a nearly-valid JSON object (for example a trailing comma or Python-literal style quoting). v0.11.1 applied a strict `json.loads()` path and failed the entire generation with errors such as `Expecting property name enclosed in double quotes`.

## Repair
- Strict JSON remains first authority.
- Deterministic local recovery is deliberately narrow: fenced-object extraction, trailing-comma removal outside quoted strings, and safe `ast.literal_eval` for Python-literal dictionaries.
- Arbitrary unquoted identifiers are not silently rewritten by local code.
- If deterministic parsing still fails, Research Director receives exactly one zero-temperature **format-only** retry. The retry is instructed to preserve scientific content and only serialize valid strict JSON.
- Recovered output still passes the unchanged `_clean_director_response`, model-registry bounds, hypothesis validation, and deterministic compiled-plan authority.
- Recovery provenance is persisted as `response_format_recovery`; if the bounded retry also fails, the generation remains fail-closed with both parse errors visible.
- Existing committed Generation evidence is not mutated; normal crash/resume re-enters only the failed Director boundary.

## Authority unchanged
LLM Scientist/Research Director remains advisory. KPI, chronology, search bounds, model registry, sealed stages, and promotion remain deterministic/Owner authorities.

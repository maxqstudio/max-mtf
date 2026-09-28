# v0.4 Provider + Research Repair

## LLM Scientist connection

- Replaced free-form endpoint/model text boxes with provider-driven connection.
- Providers: Google Gemini, OpenAI, Groq, OpenRouter, DeepSeek, Ollama Local, Custom OpenAI-compatible.
- API keys remain session-only and are never written to config or run artifacts.
- `CONNECT + TARIK MODEL` calls the provider's `/models` endpoint and populates a model dropdown.
- The Scientist now stores/uses an API **base URL** and derives `/chat/completions` itself.
- This repairs the v0.3 Gemini 404 caused by posting directly to `.../v1beta/openai/` instead of `.../v1beta/openai/chat/completions`.
- Old full endpoints ending in `/chat/completions` are normalized for backward compatibility.

## Research engine

- Random Forest baselines reduced from 500/700 trees to 240/360 trees. RF remains a diversity baseline, not the primary search engine.
- RF Scientist search bound reduced to 120–900 trees.
- Model fitting now emits a heartbeat every ~2 seconds, including elapsed time and train-row count, so a long fold no longer looks frozen.
- Fold completion now reports elapsed seconds, preview PF, expectancy and trades.
- Candidate completion reports its own score and the global best separately.
- Candidate completion also reports median PF, median expectancy, worst-fold expectancy, drawdown, validation trades and total fit time.
- `historical external: cv_leaderboard.json` now records per-fold diagnostics and fit timing.
- `historical external: research_diagnostics.json` flags all-negative candidate pools and tightly clustered top scores.
- Results UI surfaces those diagnostics instead of encouraging blind hyperparameter expansion.

## Governance unchanged

- LLM Scientist remains advisory only.
- Locked test remains hidden until winner freeze.
- Challenger/Champion authority remains deterministic and unchanged.

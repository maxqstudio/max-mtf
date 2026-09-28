# Manual Research V1

## Purpose

Manual Research lets the Owner bypass experiment proposal/search while retaining the scientific validator chain. It is intended for exact hypothesis testing, not for bypassing governance.

## Owner-controlled inputs

The Manual Candidate editor controls exact model family, exact registry-declared model hyperparameters, candidate name, exact take threshold and required minimum WFA survivors. Existing Advanced controls continue to own labels, research windows, KPI, stress, compute and other frozen run settings.

## Start contract

`START MANUAL RESEARCH` performs:

1. Compile current Owner configuration.
2. Validate every exact candidate.
3. Disable autonomous Research LLM in the runtime config.
4. Disable deterministic candidate generation/search.
5. Launch the normal owned Factory worker.
6. Run mandatory broker-backed Data Quality preflight.
7. Evaluate exact candidates by Full WFA.
8. Continue survivors to CPCV → Tournament → Monte Carlo → Fresh/Forward → Champion.

## Fail-closed rules

- Empty candidate list: block.
- Unknown family: block.
- Missing required parameter: block.
- Parameter outside legal/capacity authority: block.
- Silent numeric coercion: block.
- Invalid/unknown research mode: block.
- Zero WFA survivor or configured minimum survivor not reached: terminal `MANUAL_WFA_NO_SURVIVOR`.
- No automatic generation of replacement candidates.
- No autonomous LLM post-mortem/restart loop.

## Resume

Manual runs use the same committed Factory checkpoint/evidence rules as AUTO. Resume may continue already-committed validation stages; it must not synthesize new Owner candidates.

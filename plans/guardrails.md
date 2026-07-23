# Ralph Guardrails (Signs)

Learned constraints that prevent repeated failures. Each "sign" is a rule discovered through iteration failures. Add new signs as you encounter failure patterns.

> "Progress should persist. Failures should evaporate." - The Ralph philosophy

---

## Verification Signs

### SIGN-001: Verify Before Complete
**Trigger:** About to output completion promise
**Instruction:** ALWAYS run the verification command (`PYTHONPATH=src .venv/bin/python -m pytest`) and confirm it passes before outputting `<promise>COMPLETE</promise>`
**Reason:** Models tend to declare victory without proper verification

### SIGN-002: Check All Tasks Before Complete
**Trigger:** Completing a task in multi-task mode
**Instruction:** Re-read prd.json and count remaining `passes: false, skip != true` tasks. Only output completion promise when ALL non-skipped tasks pass.
**Reason:** Premature completion exits loop with work remaining

---

## Progress Signs

### SIGN-003: Document Learnings
**Trigger:** Completing any task
**Instruction:** Update progress.md with what was learned (patterns discovered, files modified, decisions made) before ending iteration
**Reason:** Future iterations need context to avoid re-discovering the same patterns

### SIGN-004: Small Focused Changes
**Trigger:** Making changes per iteration
**Instruction:** Keep changes small and focused. Commit incrementally when tests pass. Don't try to solve everything in one iteration.
**Reason:** Large changes are harder to debug when verification fails

---

## Task Management Signs

### SIGN-005: Use Skip for Manual Tasks
**Trigger:** Encountering a task that requires manual human intervention (creating accounts, API keys, dashboard configuration, browser-only visual confirmation)
**Instruction:** Set `skip: true` and `skipReason` in prd.json for tasks that cannot be automated. The Ralph loop will ignore skipped tasks and can complete without them.
**Reason:** Allows loop to complete automatable work without blocking on manual steps

---

## Project-Specific Signs

### SIGN-101: Always Set PYTHONPATH=src
**Trigger:** Running pytest, `python -m daol_fascope...`, or importing `daol_fascope` anywhere
**Instruction:** `daol_fascope` is an unpackaged `src/` layout module — always run with `PYTHONPATH=src` set (e.g. `PYTHONPATH=src .venv/bin/python -m pytest`). Without it, every test file fails at collection with `ModuleNotFoundError: No module named 'daol_fascope'`.
**Reason:** Discovered during Ralph setup — bare `pytest` fails to collect any test in this repo.
**Added after:** 2026-07-22 setup

### SIGN-102: Plans.md Is the Source of Truth, Not prd.json
**Trigger:** Any task in prd.json that touches scope already covered in `Plans.md`
**Instruction:** Before starting a task, read `Plans.md` (and linked `docs/adr/*.md`) for existing decisions, prior attempts, and constraints on that area. After finishing a task, ALSO update the matching row/section in `Plans.md` (status marker, 진행 메모) — not just prd.json and progress.md. prd.json is scratch state for the loop; Plans.md is the project's permanent record.
**Reason:** This repo predates Ralph and already tracks all work in Plans.md with a Korean cc:TODO/cc:완료 convention; prd.json here only covers a subset (currently Phase 3) seeded from it.
**Added after:** 2026-07-22 setup

### SIGN-103: F-002 Is Blocked, Don't Unskip Without Checking
**Trigger:** About to work on F-002 (ThingsBoard telemetry correlation widget)
**Instruction:** F-002 depends on Phase 2.5 being fully done, but as of 2026-07-22 Phase 2.5.3 still needs the user to visually confirm dashboard rendering in a browser (`http://172.16.4.228:8082`). Do not unskip F-002 until Plans.md shows Phase 2.5 status as fully complete.
**Reason:** Avoids building on top of an unverified dashboard.
**Added after:** 2026-07-22 setup

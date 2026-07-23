---
description: Plan Ralph loop tasks from Plans.md (or optionally GitHub issues)
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, TodoWrite
argument-hint: [--from-plans | --labels LABELS] [--limit N]
---

# Ralph Planner - Generate prd.json entries

This repo tracks tasks in `Plans.md` (Korean, cc:TODO/cc:완료 convention), not GitHub issues. Default source is Plans.md.

## Arguments

- `$ARGUMENTS` - Optional filters
- `--from-plans` (default) - Pull `cc:TODO` rows from Plans.md
- `--labels LABELS` - If this repo starts using GitHub issues instead, filter by labels (comma-separated)
- `--limit N` - Maximum tasks to add (default: 20)

## Instructions

<instruction>
**Step 1: Read Plans.md**

Read `Plans.md` in full. Find every task-table row whose Status column is `cc:TODO` (not `cc:완료`, not `cc:WIP`). Note its Phase, Task ID (e.g. 3.1), 내용 (description), DoD, and Depends columns.

**Step 2: Read Current prd.json**

Read `plans/prd.json`. Note which task titles/Phase-task-ids are already present (match by title similarity or an explicit reference in `notes`) to avoid duplicates.

**Step 3: Assess Each Candidate Task**

For each `cc:TODO` row not already in prd.json:

1. **Automatable?** Look for manual-only signals in the DoD/내용: "사용자가 눈으로 확인", "브라우저에서 확인", "계정 생성", "API 키 발급/대시보드 설정" (dashboard console clicking), physical/manual steps. If found, mark as `suggestSkip: true` with a Korean `skipReason`.
2. **Depends on unfinished manual work?** Check the Depends column and cross-reference other Plans.md phases — if a dependency's Status is not `cc:완료`, mark `suggestSkip: true` with reason noting the blocking phase/task.
3. **Priority**: infer from phase — treat the earliest unfinished Phase as `high`, the next as `medium`, later/Optional phases as `low`. Optional phases (explicitly marked 선택/Optional in Plans.md) never default above `medium`.

**Step 4: Present Options to User**

Use AskUserQuestion to let the user select which candidate tasks to add. Group by:
- Recommended for automation (clear DoD, no manual blockers)
- Blocked / needs skip (explain why)
- Already in prd.json (skip silently, don't ask)

**Step 5: Generate prd.json Entries**

For each selected task, generate a feature entry matching the schema already used in `plans/prd.json` (features array, `id: F-00X`, `title`, `acceptanceCriteria` derived from the DoD column, `priority`, `passes: false`, optional `skip`/`skipReason`, `notes` referencing the Plans.md phase/task-id and any 미확정/주의 callouts from that section).

**Step 6: Update prd.json**

Merge new features into the existing `features` array (don't touch or overwrite features that already have `passes: true`). Increment the `F-00X` numbering from the highest existing id.

**Step 7: Summary**

Output what was added, what was skipped and why, and suggest running `/ralph-loop --next --dry-run` to preview the first task.

**If `--labels` is passed instead of the default Plans.md source:** fall back to the original GitHub-issue-based flow (`gh issue list --state open --json ...`) — only relevant if this repo starts tracking work in GitHub issues instead of Plans.md.
</instruction>

# KO/EN language toggle for WaferScope dashboard

Status: approved (design), pending implementation plan
Scope: `nginx/waferscope.conf` only. No changes to `src/daol_fascope/setup_thingsboard_dashboard.py`, no re-provisioning of the live ThingsBoard dashboard.

## Problem

The WaferScope site (nginx-proxied ThingsBoard at `:8090`, branded via `sub_filter` in `nginx/waferscope.conf`) has Korean-only text baked into custom dashboard widgets (provisioned once by `setup_thingsboard_dashboard.py`) and into the nginx-injected chrome (sidenav menu hiding, collapse toggle). User wants a selectable KO/EN language mode, not a separate URL and not a one-way translation that drops Korean.

## Decision: Approach A (nginx DOM overlay)

All translation logic lives in the script already injected by `sub_filter` at `</head>`/`</body>` in `nginx/waferscope.conf`. This script runs in the main document (ThingsBoard's custom HTML widgets render directly into `self.ctx.$container[0]`, not an iframe, so they're reachable from the same DOM tree the existing menu-hiding script already walks).

Rejected alternative (Approach B): make each widget's JS in `setup_thingsboard_dashboard.py` language-aware via a `T()` helper, then re-push the widget JSON to the live ThingsBoard dashboard. More correct for dynamic/interpolated text, but touches most of a 1605-line file and requires re-running the "patch live dashboard in place" functions against the running instance — those are entangled with the recent random-sample run-identity fix (commit `6dfaaab`). Higher blast radius for a cosmetic feature. Not chosen.

## Architecture

Single new self-contained block added inside the existing injected `<script>` (the one that already defines `sweep()`, `hideMenus()`, `markDashboardTitles()`, `ensureToggle()`, and the `MutationObserver`).

### Components

1. **Toggle button** — `#fascope-lang-toggle`, inserted next to the existing `#fascope-menu-toggle` in `.tb-nav-header-toolbar`. Shows `"한"` when current language is English (click to switch to Korean) and `"EN"` when current language is Korean (click to switch to English) — button always shows the language you'd switch *to*. Same visual style as the existing collapse toggle.

2. **State** — `localStorage.fascopeLang`, values `'ko'` (default/unset) or `'en'`. Read once at script init.

3. **Static dictionary** — exact-string match, applied to text nodes and to `placeholder` / `aria-label` / `title` attributes. Covers:
   - Widget titles (13): "결함 검출 개요 (Defect Detection)", "Wafer Yield Map (최근 웨이퍼)", "Process Risk & Alerts (최근 원인분석)", "설비/공정 텔레메트리 ...", "공정 위험 지표 ...", "공정 단계 타임라인 ...", "Lot 선택 / 패턴별 웨이퍼 수 / Lot Trend", "Composite 웨이퍼맵 히트맵 (패턴별 평균)", "전체 웨이퍼 데이터", "모델 임계값 슬라이더", "원인분석 (최근)", "파이프라인 실행", "결함-센서 상관관계 (드래그해서 탐색)", "센서 데이터 (현재 웨이퍼)"
   - Static labels/headings/buttons (h4, div, table th, button text): "Lot 선택", "패턴별 웨이퍼 수", "랜덤 샘플 실행", "샘플링/분류", "결함 설명", "원인 분석", "심각도 판정", "해결책 제안", "심각도", "원인 가설", "권장 조치", "센서", "값", "기준평균", "편차(σ)", "X축 센서를 여기로 드래그", "Y축 센서를 여기로 드래그"
   - Placeholders: "lot 검색 (예: lot123)", "센서 검색 (예: feature_162)"
   - Static status strings with no interpolation: "로딩 중...", "불러오는 중...", "분석 중...", "요청 전송 중...", "이미 실행 중입니다", "데이터 없음", "센서 2개를 왼쪽 목록에서 드래그해서 산점도를 그려보세요"
   - Existing nginx-injected chrome (already Korean, currently untranslated): the collapse toggle's `title`/`aria-label` text ("메뉴 접기"/"메뉴 펼치기", "좌측 메뉴 접기 또는 펼치기") — these are set dynamically by `setCollapsed()` in the existing script, so that function itself picks the KO/EN string based on current `fascopeLang` rather than going through the generic dictionary pass.

   Native ThingsBoard sidenav menu item labels (e.g. "대시보드", "고객") are not currently touched by `waferscope.conf` and their language depends on the TB instance's own locale setting, which hasn't been verified. Out of scope for this change unless found to be Korean during implementation, in which case add them to the static dictionary too — TB's own text nodes are reachable by the same DOM walk.

4. **Dynamic regex rules** — ordered list of `{pattern, replace}`, applied to text nodes before the static dictionary, capturing interpolated numbers/strings:
   - `N / M 웨이퍼 로드됨` → `N / M wafers loaded`
   - `...(:PORT) 연결 실패` [`— 서버 가동 여부 확인 필요` optional suffix] → `...(:PORT) connection failed` [` — check whether the server is running`]
   - `요청 실패 (STATUS)` → `request failed (STATUS)`
   - `X vs Y (N개 웨이퍼, 클래스당 최대 200개 샘플)` → `X vs Y (N wafers, max 200 samples per class)`
   - `CLASS 소유 센서 N개 (wafer ID)` → `N sensors owned by CLASS (wafer ID)`
   - `정상 범위 (|σ|>T 센서 없음)` → `normal range (no sensors with |σ|>T)`
   - `⚠ N개 센서 임계치(|σ|>T) 초과` → `⚠ N sensors over threshold (|σ|>T)`
   - `실패 (ERR): MSG` → `failed (ERR): MSG`
   - `N개 lot 중 상위 50개 표시 (검색으로 좁히기)` → `showing top 50 of N lots (narrow with search)`
   - `모델 임계값 (Model Threshold): ` label prefix (mixed KO/EN already, only the Korean word needs swapping — folded into static dictionary instead of regex)

5. **`applyTranslations(lang)`** — folded into the existing `sweep()`. Uses `document.createTreeWalker(root, NodeFilter.SHOW_TEXT)` to visit text nodes, plus a `querySelectorAll('[placeholder],[aria-label],[title]')` pass for attributes. For each candidate:
   - On first translation, store the original string in `data-fascope-ko` on the parent element (text nodes) or alongside the attribute as `data-fascope-ko-<attr>`.
   - When `lang === 'en'`: try dynamic regex rules first (in order), then exact-dictionary lookup; if no rule matches, leave text as-is (fail-open).
   - When `lang === 'ko'`: if a `data-fascope-ko*` marker exists, restore verbatim from it (no re-translation, no drift) and clear the marker.

6. **Wiring**: toggle click → flip `localStorage.fascopeLang` → call `applyTranslations()` immediately (don't wait for the next mutation) → also re-run `ensureToggle()`'s label update. The existing `MutationObserver` callback (`sweep()`) also calls `applyTranslations()` on every mutation, so widgets that redraw their own DOM later (random-sample run, lot detail view, scatter plot) get translated as soon as they render, without needing per-widget hooks.

### Data flow

Page load → read `localStorage.fascopeLang` → initial `sweep()` (existing call already at end of script) applies translations if `en`. User interacts with a widget (selects a lot, runs random sample, drags a sensor) → widget's own JS mutates the DOM → `MutationObserver` fires → `sweep()` → `applyTranslations()` catches the new/changed text. User clicks the language toggle → `localStorage` flips → immediate `applyTranslations()` pass over the whole document.

### Error handling

Fail-open: any string not in the dictionary or not matched by a regex rule is left in its original language. No exceptions thrown, no visible breakage — worst case is a mixed-language screen for strings not yet covered. ThingsBoard's own admin/login pages are out of scope and untouched (per user's scope choice — see below).

### Scope boundary (per user decision)

Covers: Wafer Overview dashboard, Wafer Detail dashboard, and the nginx-injected sidenav (collapse toggle, hidden-menu logic already there). Does **not** cover ThingsBoard's native login page or admin/settings pages — those aren't part of this change.

### Testing

No JS test infra exists in this repo for the nginx-injected script. Verification is manual: open Wafer Overview and Wafer Detail in a browser, toggle EN/KO, confirm widget titles/labels/placeholders switch, run the random-sample flow and drag a sensor onto the scatter widget to confirm dynamically-rendered text also translates, toggle back to KO and confirm restored text matches the original exactly (byte-for-byte, via the `data-fascope-ko` round-trip).

A `ponytail:` comment will mark the regex-rule list as the deliberate simplification: new dynamic message formats added to widgets later need a matching regex rule added here, or they'll silently stay in Korean under `en`.

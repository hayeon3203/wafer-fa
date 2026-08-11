# WaferScope KO/EN Language Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a KO/EN language toggle button to the WaferScope dashboard (`:8090`) that switches all nginx-owned chrome and known dashboard-widget text between Korean and English, purely via the script `nginx/waferscope.conf` already injects with `sub_filter`.

**Architecture:** One self-contained addition to the existing injected `<script>` IIFE in `nginx/waferscope.conf` (the block that already defines `sweep()`, `hideMenus()`, `markDashboardTitles()`, `ensureToggle()`, and the `MutationObserver`). A toggle button flips `localStorage.fascopeLang` between `"ko"` (default) and `"en"`. A `applyTranslations()` function walks the live DOM with `TreeWalker` + attribute scans, translating text via an exact-match dictionary (`STATIC_DICT`) and an ordered list of regex rules (`DYNAMIC_RULES`) for interpolated status messages, storing originals in a `WeakMap` so switching back to Korean restores byte-for-byte. No other file changes; no live ThingsBoard re-provisioning.

**Tech Stack:** nginx `sub_filter`, vanilla JS (ES5-style, matching the existing injected script's style), no build step — `nginx/waferscope.conf` is bind-mounted read-only into the `daol-fascope-waferscope-nginx` container (`docker-compose.yml`), so edits take effect on `nginx -s reload`, no image rebuild or container restart needed.

## Global Constraints

- Touch only `nginx/waferscope.conf`. Do not modify `src/daol_fascope/setup_thingsboard_dashboard.py` or push anything to the live ThingsBoard dashboard via its API.
- The whole injected script is the value of a **single-quoted** `sub_filter` argument. Every new JS string literal MUST use double quotes (`"..."`), never single quotes, and English translation text must never contain an apostrophe (write "does not" not "doesn't") — an embedded `'` would terminate the nginx directive early and break the config. (Verified: nginx's config parser accepts raw newlines inside a quoted directive argument, so the new blocks below can stay multi-line for readability — confirmed with a scratch `nginx -t` test against a multi-line `sub_filter` value.)
- Default language is Korean (`localStorage.fascopeLang` unset or anything other than `"en"` = Korean). The toggle button always displays the language you would switch **to** (`"EN"` while Korean is active, `"한"` while English is active).
- Fail-open: any string not covered by `STATIC_DICT` or `DYNAMIC_RULES` is left exactly as-is. No exceptions may propagate out of `applyTranslations()`.
- No JS test framework exists in this repo for the injected script. Each task's "test" step is: (1) `docker exec daol-fascope-waferscope-nginx nginx -t` for syntax, (2) `docker exec daol-fascope-waferscope-nginx nginx -s reload` to apply, (3) a `curl`-based grep against the served HTML as a fast automated proxy that the new source text actually shipped, (4) a manual browser check for the actual runtime behavior (curl only fetches the raw HTML/script text, not what Angular+our script render).
- Reference spec: `docs/superpowers/specs/2026-08-11-ko-en-toggle-design.md`.

---

## File Structure

Only one file changes:
- Modify: `nginx/waferscope.conf` — the `sub_filter '</head>' '...'` CSS block (currently line 32) gets 4 new small rules appended before `</style>`; the `sub_filter '</body>' '...'` JS block (currently line 36) gets new functions and two modified lines inserted into the existing IIFE.

No new files.

---

### Task 1: Language toggle button + state scaffolding

**Files:**
- Modify: `nginx/waferscope.conf`

**Interfaces:**
- Produces (used by Task 2 and Task 3): `getLang()` → `"ko"|"en"`, `setLang(v)`, `LANG_KEY` (localStorage key `"fascopeLang"`), `koMap` (a `WeakMap`), a stub `function applyTranslations(){}` that Task 2 replaces with the real implementation, `ensureLangToggle()`, `updateLangToggleLabel()`.

- [ ] **Step 1: Add CSS for the new toggle button**

In `nginx/waferscope.conf`, inside the `sub_filter '</head>' '...'` argument (the giant CSS string), find this exact substring (it currently appears once, right after the existing menu-toggle hover rule and right before the `@media(min-width:960px)` block):

```
#fascope-menu-toggle:hover{background:rgba(255,255,255,.16)!important}@media(min-width:960px){
```

Replace it with:

```
#fascope-menu-toggle:hover{background:rgba(255,255,255,.16)!important}#fascope-lang-toggle{position:absolute;right:52px;top:14px;z-index:3;height:36px;padding:0 10px;border:0;border-radius:8px;background:rgba(255,255,255,.08);color:#fff!important;cursor:pointer;font-size:13px;font-family:Roboto,Arial,sans-serif;line-height:36px}#fascope-lang-toggle:hover{background:rgba(255,255,255,.16)!important}html.fascope-menu-collapsed #fascope-lang-toggle{display:none!important}@media(max-width:959px){#fascope-lang-toggle{display:none!important}}@media(min-width:960px){
```

- [ ] **Step 2: Add `LANG_KEY`, `koMap`, `getLang()`, and the `applyTranslations()` stub**

In the same file, inside the `sub_filter '</body>' '...'` argument, find this exact substring:

```
KEY="fascopeMenuCollapsed";function setCollapsed(v){
```

Replace it with:

```
KEY="fascopeMenuCollapsed",LANG_KEY="fascopeLang",koMap=new WeakMap();function getLang(){return localStorage.getItem(LANG_KEY)==="en"?"en":"ko";}function applyTranslations(){}function setCollapsed(v){
```

- [ ] **Step 3: Make the collapse-toggle title/aria-label language-aware**

In the same argument, find this exact substring:

```
b.title=v?"메뉴 펼치기":"메뉴 접기";
```

Replace it with:

```
var fascopeEn=getLang()==="en";b.title=fascopeEn?(v?"Expand menu":"Collapse menu"):(v?"메뉴 펼치기":"메뉴 접기");b.setAttribute("aria-label",fascopeEn?"Collapse or expand the left menu":"좌측 메뉴 접기 또는 펼치기");
```

- [ ] **Step 4: Add the language-toggle button + `setLang()`, remove the now-redundant static aria-label**

In the same argument, find this exact substring:

```
b.setAttribute("aria-label","좌측 메뉴 접기 또는 펼치기");b.addEventListener("click",function(){var v=!document.documentElement.classList.contains("fascope-menu-collapsed");localStorage.setItem(KEY,v?"1":"0");setCollapsed(v);});bar.appendChild(b);setCollapsed(localStorage.getItem(KEY)==="1");}
```

Replace it with:

```
b.addEventListener("click",function(){var v=!document.documentElement.classList.contains("fascope-menu-collapsed");localStorage.setItem(KEY,v?"1":"0");setCollapsed(v);});bar.appendChild(b);setCollapsed(localStorage.getItem(KEY)==="1");}function updateLangToggleLabel(){var b=document.getElementById("fascope-lang-toggle");if(b){b.textContent=getLang()==="en"?"한":"EN";}}function ensureLangToggle(){if(document.getElementById("fascope-lang-toggle")){updateLangToggleLabel();return;}var bar=document.querySelector("mat-sidenav.tb-site-sidenav .tb-nav-header-toolbar");if(!bar)return;var b=document.createElement("button");b.id="fascope-lang-toggle";b.type="button";b.title="Switch language";b.addEventListener("click",function(e){e.stopPropagation();setLang(getLang()==="en"?"ko":"en");});bar.appendChild(b);updateLangToggleLabel();}function setLang(v){localStorage.setItem(LANG_KEY,v);var collapsed=document.documentElement.classList.contains("fascope-menu-collapsed");setCollapsed(collapsed);updateLangToggleLabel();applyTranslations();}
```

(Note: `b.setAttribute("aria-label",...)` was removed from the start of this substring — Step 3's change to `setCollapsed` now sets it instead, since `ensureToggle()` already calls `setCollapsed(...)` right after appending the button.)

- [ ] **Step 5: Wire the new button into `sweep()`**

In the same argument, find this exact substring:

```
function sweep(){hideMenus();markDashboardTitles();ensureToggle();}
```

Replace it with:

```
function sweep(){hideMenus();markDashboardTitles();ensureToggle();ensureLangToggle();applyTranslations();}
```

- [ ] **Step 6: Validate nginx config syntax**

Run: `docker exec daol-fascope-waferscope-nginx nginx -t`
Expected: `syntax is ok` / `test is successful`

- [ ] **Step 7: Reload nginx and smoke-check via curl**

Run:
```bash
docker exec daol-fascope-waferscope-nginx nginx -s reload
curl -s http://localhost:8090/ | grep -c 'fascope-lang-toggle'
```
Expected: a number ≥ 1 (the button-creation code shipped in the response body).

- [ ] **Step 8: Manual browser check**

Open `http://<host>:8090`, log in, go to "Wafer Overview". Confirm:
- A second small button (labeled `EN`) sits to the left of the existing collapse-arrow button.
- Clicking it flips its label to `한`, and hovering the collapse-arrow button now shows an English tooltip ("Collapse menu" / "Expand menu").
- Clicking again flips back to `EN` and the Korean tooltip returns.
- No content has translated yet (expected — that's Task 2/3).

- [ ] **Step 9: Commit**

```bash
git add nginx/waferscope.conf
git commit -m "$(cat <<'EOF'
feat: add KO/EN language toggle button scaffolding to WaferScope

Adds the toggle button, localStorage-backed language state, and a no-op
applyTranslations() stub that Task 2 fills in. No content translates yet.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Static dictionary translation

**Files:**
- Modify: `nginx/waferscope.conf`

**Interfaces:**
- Consumes: `getLang()`, `koMap`, `LANG_KEY` from Task 1.
- Produces (used by Task 3): `STATIC_DICT` (object, Korean trimmed string → English string), `translateFragment(raw)` → translated string with original leading/trailing whitespace preserved, or `null` if no match, `applyTranslations()` (full implementation, replaces Task 1's stub).

- [ ] **Step 1: Replace the `applyTranslations` stub with the dictionary + real implementation**

Find this exact substring (the stub added in Task 1):

```
function applyTranslations(){}
```

Replace it with:

```
var STATIC_DICT={"결함 검출 개요 (Defect Detection)":"Defect Detection Overview","Wafer Yield Map (최근 웨이퍼)":"Wafer Yield Map (Recent Wafer)","Process Risk & Alerts (최근 원인분석)":"Process Risk & Alerts (Recent Root Cause)","설비/공정 텔레메트리":"Equipment/Process Telemetry","설비/공정 텔레메트리 (Phase 3 예정 — 챔버 온도, 로봇 상태 등 합성 장비 로그 연동 후 채워짐)":"Equipment/Process Telemetry (Phase 3 planned — populated once synthetic equipment logs like chamber temperature and robot status are wired up)","공정 위험 지표":"Process Risk Indicators","공정 위험 지표 (Phase 3 예정 — 실시간 이상탐지 알림)":"Process Risk Indicators (Phase 3 planned — real-time anomaly alerts)","공정 단계 타임라인":"Process Stage Timeline","공정 단계 타임라인 (Phase 3 예정 — SECS/GEM 합성 로그 기반 공정 진행률)":"Process Stage Timeline (Phase 3 planned — SECS/GEM synthetic-log-based process progress)","Lot 선택 / 패턴별 웨이퍼 수 / Lot Trend":"Lot Selection / Wafer Count by Pattern / Lot Trend","Composite 웨이퍼맵 히트맵 (패턴별 평균)":"Composite Wafer Map Heatmap (Average by Pattern)","전체 웨이퍼 데이터":"All Wafer Data","모델 임계값 슬라이더":"Model Threshold Slider","원인분석 (최근)":"Root Cause Analysis (Recent)","파이프라인 실행":"Pipeline Run","결함-센서 상관관계 (드래그해서 탐색)":"Defect-Sensor Correlation (drag to explore)","센서 데이터 (현재 웨이퍼)":"Sensor Data (Current Wafer)","Lot 선택":"Select Lot","패턴별 웨이퍼 수 ":"Wafer Count by Pattern ","모델 임계값 (Model Threshold): ":"Model Threshold: ","랜덤 샘플 실행":"Run Random Sample","샘플링/분류":"Sample / Classify","결함 설명":"Describe Defect","원인 분석":"Root Cause","심각도 판정":"Assess Severity","해결책 제안":"Suggest Recipe","X축 센서를 여기로 드래그":"Drag X-axis sensor here","Y축 센서를 여기로 드래그":"Drag Y-axis sensor here","센서 2개를 왼쪽 목록에서 드래그해서 산점도를 그려보세요":"Drag 2 sensors from the list on the left to plot them","센서":"Sensor","값":"Value","기준평균":"Baseline Mean","편차(σ)":"Deviation (σ)","심각도":"Severity","원인 가설":"Root Cause Hypothesis","권장 조치":"Recommended Action","로딩 중...":"Loading...","불러오는 중...":"Loading...","분석 중...":"Analyzing...","요청 전송 중...":"Sending request...","이미 실행 중입니다":"Already running","데이터 없음":"No data","lot 검색 (예: lot123)":"Search lot (e.g. lot123)","센서 검색 (예: feature_162)":"Search sensor (e.g. feature_162)"};function translateFragment(raw){var trimmed=raw.trim();if(!trimmed)return null;var lead=raw.slice(0,raw.length-raw.replace(/^\s+/,"").length);var trail=raw.slice(raw.replace(/\s+$/,"").length);var out=null;if(Object.prototype.hasOwnProperty.call(STATIC_DICT,trimmed)){out=STATIC_DICT[trimmed];}return out===null?null:(lead+out+trail);}function applyTranslations(){var lang=getLang();var walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode:function(n){var tag=n.parentNode&&n.parentNode.nodeName;if(tag==="SCRIPT"||tag==="STYLE")return NodeFilter.FILTER_REJECT;return NodeFilter.FILTER_ACCEPT;}});var node,textNodes=[];while((node=walker.nextNode()))textNodes.push(node);textNodes.forEach(function(n){if(lang==="en"){if(!koMap.has(n)){var translated=translateFragment(n.nodeValue);if(translated!==null){koMap.set(n,n.nodeValue);n.nodeValue=translated;}}}else if(koMap.has(n)){n.nodeValue=koMap.get(n);koMap.delete(n);}});["placeholder","aria-label","title"].forEach(function(attr){document.querySelectorAll("["+attr+"]").forEach(function(el){if(el.id==="fascope-menu-toggle"||el.id==="fascope-lang-toggle")return;var markAttr="data-fascope-ko-"+attr;if(lang==="en"){if(!el.hasAttribute(markAttr)){var original=el.getAttribute(attr);var translated=translateFragment(original);if(translated!==null){el.setAttribute(markAttr,original);el.setAttribute(attr,translated);}}}else if(el.hasAttribute(markAttr)){el.setAttribute(attr,el.getAttribute(markAttr));el.removeAttribute(markAttr);}});});}
```

- [ ] **Step 2: Validate nginx config syntax**

Run: `docker exec daol-fascope-waferscope-nginx nginx -t`
Expected: `syntax is ok` / `test is successful`

- [ ] **Step 3: Reload nginx and smoke-check via curl**

Run:
```bash
docker exec daol-fascope-waferscope-nginx nginx -s reload
curl -s http://localhost:8090/ | grep -c 'Defect Detection Overview'
```
Expected: a number ≥ 1.

- [ ] **Step 4: Manual browser check**

Open Wafer Overview and Wafer Detail with the language toggle set to `EN` (click it if needed). Confirm:
- Widget titles are in English (e.g. "Wafer Yield Map (Recent Wafer)", "Model Threshold Slider", "All Wafer Data").
- Static labels are in English: the "Select Lot" panel title, the pipeline step labels ("Sample / Classify", "Describe Defect", "Root Cause", "Assess Severity", "Suggest Recipe"), the sensor table headers ("Sensor", "Value", "Baseline Mean", "Deviation (σ)"), the lot/sensor search placeholders.
- Toggle back to `한` (Korean) and confirm every one of the above reverts to its exact original Korean text (spot-check a few against a fresh private/incognito window, which still defaults to Korean, to compare).

- [ ] **Step 5: Commit**

```bash
git add nginx/waferscope.conf
git commit -m "$(cat <<'EOF'
feat: translate static WaferScope widget text for EN language mode

Wires the toggle scaffolding from the previous commit up to a full
dictionary-based DOM text/attribute translator. Dynamic interpolated
status messages (loading counts, connection errors, etc.) are still
Korean-only in EN mode -- next commit adds those.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Dynamic (interpolated) message translation

**Files:**
- Modify: `nginx/waferscope.conf`

**Interfaces:**
- Consumes: `translateFragment(raw)` from Task 2 (its internal matching logic is replaced by this task; its external signature — input a raw string, output translated string or `null` — is unchanged, so nothing else needs to change).
- Produces: `DYNAMIC_RULES` (ordered array of `[RegExp, String]` pairs).

- [ ] **Step 1: Add `DYNAMIC_RULES` and extend `translateFragment` to consult it**

Find this exact substring (the `translateFragment` body from Task 2):

```
function translateFragment(raw){var trimmed=raw.trim();if(!trimmed)return null;var lead=raw.slice(0,raw.length-raw.replace(/^\s+/,"").length);var trail=raw.slice(raw.replace(/\s+$/,"").length);var out=null;if(Object.prototype.hasOwnProperty.call(STATIC_DICT,trimmed)){out=STATIC_DICT[trimmed];}return out===null?null:(lead+out+trail);}
```

Replace it with:

```
var DYNAMIC_RULES=[[/^(\d+) \/ (\d+) 웨이퍼 로드됨$/,"$1 / $2 wafers loaded"],[/ 연결 실패 — 서버 가동 여부 확인 필요$/," connection failed — check whether the server is running"],[/ 연결 실패$/," connection failed"],[/^요청 실패 \((.+)\)$/,"request failed ($1)"],[/^(.+) vs (.+) \((\d+)개 웨이퍼, 클래스당 최대 200개 샘플\)$/,"$1 vs $2 ($3 wafers, max 200 samples per class)"],[/^(.+) 소유 센서 (\d+)개 \(wafer (.+)\)$/,"$2 sensors owned by $1 (wafer $3)"],[/^정상 범위 \(\|σ\|>(.+) 센서 없음\)$/,"normal range (no sensors with |σ|>$1)"],[/^⚠ (\d+)개 센서 임계치\(\|σ\|>(.+)\) 초과$/,"⚠ $1 sensors over threshold (|σ|>$2)"],[/^실패 \((.+?)\):\s*(.*)$/,"failed ($1): $2"],[/^(\d+)개 lot 중 상위 50개 표시 \(검색으로 좁히기\)$/,"$1 lots found — showing top 50 (narrow your search)"],[/\(값 ([^)]+)\)/,"(value $1)"]];function translateFragment(raw){var trimmed=raw.trim();if(!trimmed)return null;var lead=raw.slice(0,raw.length-raw.replace(/^\s+/,"").length);var trail=raw.slice(raw.replace(/\s+$/,"").length);var out=null;if(Object.prototype.hasOwnProperty.call(STATIC_DICT,trimmed)){out=STATIC_DICT[trimmed];}else{for(var i=0;i<DYNAMIC_RULES.length;i++){if(DYNAMIC_RULES[i][0].test(trimmed)){out=trimmed.replace(DYNAMIC_RULES[i][0],DYNAMIC_RULES[i][1]);break;}}}return out===null?null:(lead+out+trail);}
```

Note the second rule's replacement string keeps its leading space (`" connection failed — check whether the server is running"`) — the regex match consumes the leading space from the original Korean text, and the character right before the match (e.g. `wafer_browser_server(:8091)`) has no trailing space of its own, so the replacement must supply one to avoid `...8091)connection failed`.

- [ ] **Step 2: Validate nginx config syntax**

Run: `docker exec daol-fascope-waferscope-nginx nginx -t`
Expected: `syntax is ok` / `test is successful`

- [ ] **Step 3: Reload nginx and smoke-check via curl**

Run:
```bash
docker exec daol-fascope-waferscope-nginx nginx -s reload
curl -s http://localhost:8090/ | grep -c 'wafers loaded'
```
Expected: a number ≥ 1.

- [ ] **Step 4: Manual browser check**

With the language toggle set to `EN`:
- On "Wafer Detail", click "Run Random Sample" (pipeline widget) and watch it move through stages; confirm any status text (e.g. "Sending request...", "Already running") reads in English.
- On "Wafer Overview", drag two sensors onto the correlation scatter widget's X/Y drop zones; confirm the resulting status line reads like "feature_12 vs feature_88 (37 wafers, max 200 samples per class)".
- In the Lot selector search box, type a partial lot id that matches more than 50 lots (or check the hint text as soon as it appears) and confirm it reads like "N lots found — showing top 50 (narrow your search)".
- If reachable, disconnect/stop one of the backend servers (or just note the pattern) and confirm a connection-failure message reads like "wafer_predict_server(:8092) connection failed" in English.
- Toggle back to `한` and spot-check that a couple of these dynamic messages restore to Korean on their next update (they won't retroactively restore stale text already on screen from before the toggle if the widget hasn't refreshed it since — matches the design spec's documented fail-open behavior for the `WeakMap`-tracked live text).

- [ ] **Step 5: Commit**

```bash
git add nginx/waferscope.conf
git commit -m "$(cat <<'EOF'
feat: translate dynamic interpolated status messages for EN mode

Adds regex-based DYNAMIC_RULES to translateFragment() so counts,
connection-failure messages, and other data-interpolated widget status
text also switch language, not just static labels.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: End-to-end acceptance walkthrough

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Fresh-session walkthrough**

In a private/incognito browser window (clean `localStorage`), open `http://<host>:8090`, log in, and confirm the site loads entirely in Korean by default (unchanged from before this feature).

- [ ] **Step 2: Full EN pass**

Click the language toggle on Wafer Overview. Visit every widget on both Wafer Overview and Wafer Detail and confirm every string catalogued in `docs/superpowers/specs/2026-08-11-ko-en-toggle-design.md`'s "Static dictionary" and "Dynamic regex rules" sections is in English. Note any remaining Korean strings you find (expected: ThingsBoard's own native sidenav menu item labels, since those were called out in the spec as depending on the TB instance's own locale and out of scope unless found Korean).

- [ ] **Step 3: Round-trip check**

Toggle back to `한`. Reload the page. Confirm the language preference persisted (still Korean) and every widget shows its original Korean text, byte-for-byte, with no leftover English fragments or broken layout.

- [ ] **Step 4: Report findings**

If Step 2 found native ThingsBoard chrome still in Korean and the user wants it covered too, that's a follow-up (add those exact strings to `STATIC_DICT` in a new small commit) rather than a plan revision — the dictionary/rule-list design already supports it with no structural change.

No commit for this task (verification only).

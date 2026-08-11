# WaferScope KO/EN Language Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a KO/EN language toggle button to the WaferScope dashboard (`:8090`) that switches all nginx-owned chrome and known dashboard-widget text between Korean and English.

**Architecture:** A toggle button flips `localStorage.fascopeLang` between `"ko"` (default) and `"en"`. An `applyTranslations()` function walks the live DOM with `TreeWalker` + attribute scans, translating text via an exact-match dictionary (`STATIC_DICT`) and an ordered list of regex rules (`DYNAMIC_RULES`) for interpolated status messages, storing originals in a `WeakMap` so switching back to Korean restores byte-for-byte. No live ThingsBoard re-provisioning.

**REVISED after Task 2 (original numbering) took the site down — see "Incident and Architecture Revision" below.** The script is served as a real static file (`nginx/fascope-lang.js`), not injected inline via `sub_filter`. `nginx/waferscope.conf` only injects a tiny `<script src="...">` tag.

**Tech Stack:** nginx `sub_filter` + a static-file `location` block, vanilla JS (no build step). `nginx/fascope-lang.js` and `nginx/waferscope.conf` are bind-mounted read-only into the `daol-fascope-waferscope-nginx` container (`docker-compose.yml`).

## Incident and Architecture Revision (read before touching anything)

Executing this plan's original Task 2 (inline `STATIC_DICT` injected via `sub_filter`) took the live WaferScope site down. Root causes, confirmed by direct reproduction in a throwaway `nginx:alpine` container:

1. **nginx has a hard ~4096-byte limit per quoted config directive argument** (`NGX_CONF_BUFFER`) that does not grow. Verified empirically: a quoted value of 4090 bytes parses fine, 4096 bytes fails with `too long parameter, probably missing terminating "'" character`. The original design's single giant `sub_filter '</body>' '<script>...</script></body>'` value was ~1.9KB after Task 1 (fine) and ~6.5KB after Task 2's dictionary addition (over the limit — config parse failure — container crash-loop).
2. **This went undetected during Task 1 and the first Task 2 attempt** because `docker exec daol-fascope-waferscope-nginx nginx -t` was silently validating a *stale* file. Docker's single-file bind mount pins the container to the host file's **inode**, not its path. Standard atomic-write patterns (write a temp file, then rename over the target — what most editors and file-writing tools do) replace the inode on every edit, silently detaching the bind mount from the file you keep editing on the host. `nginx -t` inside the container kept passing because it was reading old, already-deployed content, not the new edit.

**Fix applied:** the site was restored by reverting to the last known-good commit and restarting the container (commit `bf72a07`). The design is revised so the injected content can never hit the 4096-byte ceiling again: the actual script logic moves to a real file (`nginx/fascope-lang.js`) served through a normal nginx `location` block, and `waferscope.conf`'s `sub_filter` only ever injects a short, constant-size `<script src="...">` tag. A static file has no directive-length limit at all.

**Standing process fix for every task below:** after editing *any* bind-mounted file, verify the container actually received it before trusting `nginx -t`/`curl`:

```bash
docker exec daol-fascope-waferscope-nginx md5sum /etc/nginx/conf.d/default.conf
md5sum nginx/waferscope.conf
# and, once it exists:
docker exec daol-fascope-waferscope-nginx md5sum /etc/nginx/custom/fascope-lang.js
md5sum nginx/fascope-lang.js
```

If the sums don't match, `nginx -s reload` will not fix it — run `docker restart daol-fascope-waferscope-nginx` instead (not just reload) to re-establish the bind mounts, then re-run the md5sum check before proceeding to `nginx -t`.

## Global Constraints

- File scope is now: `nginx/waferscope.conf` (small edits), `docker-compose.yml` (one new volume line), `nginx/fascope-lang.js` (new file, holds all injected-script logic). Do not modify `src/daol_fascope/setup_thingsboard_dashboard.py` or push anything to the live ThingsBoard dashboard via its API.
- `nginx/fascope-lang.js` is a normal JS file with no length constraint and no quoting constraint — write it readably, multi-line, whatever quote style is natural.
- `nginx/waferscope.conf`'s remaining `sub_filter` values are still single-quoted nginx directive arguments: any string literal placed directly inside one of those `sub_filter` calls (not inside `fascope-lang.js`) must still use double quotes only, no apostrophes. After the final fix wave, the CSS block was also extracted out to a real file (`nginx/fascope.css`, served via its own `location` block), the same pattern already proven for the JS. Both remaining `sub_filter` values now only ever inject tiny fixed-size tags — `<link rel="stylesheet" href="/assets/fascope.css">` and `<script src="/assets/fascope-lang.js"></script>` — so there is no remaining directive-length risk at all.
- Default language is Korean (`localStorage.fascopeLang` unset or anything other than `"en"` = Korean). The toggle button always displays the language you would switch **to** (`"EN"` while Korean is active, `"한"` while English is active).
- Fail-open: any string not covered by `STATIC_DICT` or `DYNAMIC_RULES` is left exactly as-is. No exceptions may propagate out of `applyTranslations()`.
- No JS test framework exists in this repo. Each task's "test" step is: (1) the md5sum bind-mount check above, (2) `docker exec daol-fascope-waferscope-nginx nginx -t` for syntax, (3) `docker exec daol-fascope-waferscope-nginx nginx -s reload` (or `docker restart` if the md5sum check required it) to apply, (4) a `curl`-based grep against the served HTML/JS as a fast automated proxy, (5) a manual browser check for actual runtime behavior.
- Reference spec: `docs/superpowers/specs/2026-08-11-ko-en-toggle-design.md` (still architecturally accurate — the DOM-overlay translation approach is unchanged; only the delivery mechanism for the script itself changed).

---

## File Structure

- Modify: `nginx/waferscope.conf` — add a `location = /assets/fascope-lang.js` block; shrink the `sub_filter '</body>' '...'` value to just inject a `<script src>` tag.
- Modify: `docker-compose.yml` — add one bind-mount line for `nginx/fascope-lang.js` under the `waferscope-nginx` service.
- Create: `nginx/fascope-lang.js` — all injected-script logic (menu hiding, dashboard title marking, collapse toggle, language toggle, translation dictionary/rules).

---

### Task 1: Language toggle button + state scaffolding — DONE

Completed and reviewed clean (commit `3473d6c`). No action needed. Recorded here for history only; do not re-run.

---

### Task 2: Extract the injected script to `nginx/fascope-lang.js`

Pure refactor — behavior must be identical to the current live site (Task 1's state) before and after. No new features, no translation content yet (`applyTranslations` stays a no-op stub).

**Files:**
- Create: `nginx/fascope-lang.js`
- Modify: `nginx/waferscope.conf`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces (used by Task 3 and Task 4): the file `nginx/fascope-lang.js` containing `getLang()`, `setLang(v)`, `LANG_KEY`, `koMap`, a stub `function applyTranslations() {}`, `ensureLangToggle()`, `updateLangToggleLabel()`, `sweep()` — same names and behavior as the current inline script, just relocated.

- [ ] **Step 1: Create `nginx/fascope-lang.js` with the current script's exact logic, reformatted readably**

Create `/home/admin/daol-fascope/nginx/fascope-lang.js`:

```javascript
(function () {
  var L = ["개체", "Edge management"];
  var D = ["Wafer Overview", "Wafer Detail"];
  var KEY = "fascopeMenuCollapsed";
  var LANG_KEY = "fascopeLang";
  var koMap = new WeakMap();

  function getLang() {
    return localStorage.getItem(LANG_KEY) === "en" ? "en" : "ko";
  }

  function applyTranslations() {}

  function setCollapsed(v) {
    document.documentElement.classList.toggle("fascope-menu-collapsed", v);
    var b = document.getElementById("fascope-menu-toggle");
    if (b) {
      b.textContent = v ? "chevron_right" : "chevron_left";
      b.setAttribute("aria-expanded", v ? "false" : "true");
      var fascopeEn = getLang() === "en";
      b.title = fascopeEn ? (v ? "Expand menu" : "Collapse menu") : (v ? "메뉴 펼치기" : "메뉴 접기");
      b.setAttribute("aria-label", fascopeEn ? "Collapse or expand the left menu" : "좌측 메뉴 접기 또는 펼치기");
    }
    setTimeout(function () {
      window.dispatchEvent(new Event("resize"));
    }, 220);
  }

  function ensureToggle() {
    if (document.getElementById("fascope-menu-toggle")) return;
    var bar = document.querySelector("mat-sidenav.tb-site-sidenav .tb-nav-header-toolbar");
    if (!bar) return;
    var b = document.createElement("button");
    b.id = "fascope-menu-toggle";
    b.type = "button";
    b.className = "material-icons";
    b.addEventListener("click", function () {
      var v = !document.documentElement.classList.contains("fascope-menu-collapsed");
      localStorage.setItem(KEY, v ? "1" : "0");
      setCollapsed(v);
    });
    bar.appendChild(b);
    setCollapsed(localStorage.getItem(KEY) === "1");
  }

  function updateLangToggleLabel() {
    var b = document.getElementById("fascope-lang-toggle");
    if (b) {
      b.textContent = getLang() === "en" ? "한" : "EN";
    }
  }

  function ensureLangToggle() {
    if (document.getElementById("fascope-lang-toggle")) {
      updateLangToggleLabel();
      return;
    }
    var bar = document.querySelector("mat-sidenav.tb-site-sidenav .tb-nav-header-toolbar");
    if (!bar) return;
    var b = document.createElement("button");
    b.id = "fascope-lang-toggle";
    b.type = "button";
    b.title = "Switch language";
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      setLang(getLang() === "en" ? "ko" : "en");
    });
    bar.appendChild(b);
    updateLangToggleLabel();
  }

  function setLang(v) {
    localStorage.setItem(LANG_KEY, v);
    var collapsed = document.documentElement.classList.contains("fascope-menu-collapsed");
    setCollapsed(collapsed);
    updateLangToggleLabel();
    applyTranslations();
  }

  function hideMenus() {
    document.querySelectorAll("a.tb-button-toggle").forEach(function (a) {
      var t = a.textContent || "";
      if (L.some(function (l) { return t.indexOf(l) !== -1; })) {
        (a.closest("li") || a).remove();
      }
    });
  }

  function markDashboardTitles() {
    document.querySelectorAll("mat-toolbar,[class*=dashboard-title]").forEach(function (el) {
      var t = (el.textContent || "").trim();
      if (D.some(function (d) { return t.indexOf(d) !== -1; })) {
        var bar = el.closest("mat-toolbar") || el;
        bar.classList.add("fascope-dashboard-title-bar");
      }
    });
  }

  function sweep() {
    hideMenus();
    markDashboardTitles();
    ensureToggle();
    ensureLangToggle();
    applyTranslations();
  }

  new MutationObserver(sweep).observe(document.documentElement, { childList: true, subtree: true });
  setCollapsed(localStorage.getItem(KEY) === "1");
  sweep();
})();
```

- [ ] **Step 2: Shrink the inline script in `nginx/waferscope.conf` to a `<script src>` tag**

In `nginx/waferscope.conf`, find the `sub_filter '</body>' '...'` line (currently one long line containing the entire inline script — it starts with `sub_filter '</body>' '<script>(function(){var L=` and ends with `sweep();})();</script></body>';`). Replace the whole line with:

```
        sub_filter '</body>' '<script src="/assets/fascope-lang.js"></script></body>';
```

- [ ] **Step 3: Add the static-file location block for the new script**

In the same file, find:

```
    location = /assets/logo_title_white.svg {
        alias /etc/nginx/custom/logo_title_white.svg;
    }
```

Replace it with:

```
    location = /assets/logo_title_white.svg {
        alias /etc/nginx/custom/logo_title_white.svg;
    }

    location = /assets/fascope-lang.js {
        alias /etc/nginx/custom/fascope-lang.js;
        default_type application/javascript;
    }
```

- [ ] **Step 4: Add the bind mount in `docker-compose.yml`**

Find, under the `waferscope-nginx` service:

```
    volumes:
      - ./nginx/waferscope.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/waferscope.ico:/etc/nginx/custom/waferscope.ico:ro
      - ./nginx/logo_title_white.svg:/etc/nginx/custom/logo_title_white.svg:ro
```

Replace it with:

```
    volumes:
      - ./nginx/waferscope.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/waferscope.ico:/etc/nginx/custom/waferscope.ico:ro
      - ./nginx/logo_title_white.svg:/etc/nginx/custom/logo_title_white.svg:ro
      - ./nginx/fascope-lang.js:/etc/nginx/custom/fascope-lang.js:ro
```

- [ ] **Step 5: Recreate the container (a new bind mount requires this, `restart` is not enough)**

```bash
cd /home/admin/daol-fascope
docker compose up -d waferscope-nginx
sleep 2
docker ps --filter name=daol-fascope-waferscope-nginx --format '{{.Status}}'
```
Expected: `Up ...` (not `Restarting`).

- [ ] **Step 6: Verify the bind mounts actually match (the standing process fix)**

```bash
docker exec daol-fascope-waferscope-nginx md5sum /etc/nginx/conf.d/default.conf /etc/nginx/custom/fascope-lang.js
md5sum nginx/waferscope.conf nginx/fascope-lang.js
```
Expected: each pair of sums matches. If not, `docker restart daol-fascope-waferscope-nginx` and re-check before continuing.

- [ ] **Step 7: Validate nginx config syntax and reload**

```bash
docker exec daol-fascope-waferscope-nginx nginx -t
docker exec daol-fascope-waferscope-nginx nginx -s reload
```
Expected: `syntax is ok` / `test is successful`.

- [ ] **Step 8: curl smoke checks**

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8090/
curl -s http://localhost:8090/assets/fascope-lang.js | grep -c 'ensureLangToggle'
curl -s http://localhost:8090/ | grep -c 'fascope-lang.js'
```
Expected: `200`, then a number ≥ 1 for each grep.

- [ ] **Step 9: Manual browser check — confirm zero behavior change from Task 1**

Open `http://<host>:8090`, log in, go to "Wafer Overview". Confirm exactly what Task 1 confirmed: the `EN`/`한` toggle button appears next to the collapse arrow, clicking it flips the label and the collapse-button's tooltip language, no content translates yet. This must look and behave identically to before this task — it's a pure refactor.

- [ ] **Step 10: Commit**

```bash
git add nginx/fascope-lang.js nginx/waferscope.conf docker-compose.yml
git commit -m "$(cat <<'EOF'
refactor: serve WaferScope's injected script as a static file

nginx has a hard ~4096-byte limit per quoted sub_filter argument that
the next task's translation dictionary would exceed. Move the script
out of the inline sub_filter into nginx/fascope-lang.js, served via a
normal location block, so there's no size ceiling for what follows.
Pure refactor -- no behavior change.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Static dictionary translation

**Files:**
- Modify: `nginx/fascope-lang.js`

**Interfaces:**
- Consumes: `getLang()`, `koMap`, `LANG_KEY` from Task 2.
- Produces (used by Task 4): `STATIC_DICT` (object, Korean trimmed string → English string), `translateFragment(raw)` → translated string with original leading/trailing whitespace preserved, or `null` if no match, `applyTranslations()` (full implementation, replaces Task 2's stub).

- [ ] **Step 1: Replace the `applyTranslations` stub with the dictionary + real implementation**

In `nginx/fascope-lang.js`, find:

```javascript
  function applyTranslations() {}
```

Replace it with:

```javascript
  var STATIC_DICT = {
    "결함 검출 개요 (Defect Detection)": "Defect Detection Overview",
    "Wafer Yield Map (최근 웨이퍼)": "Wafer Yield Map (Recent Wafer)",
    "Process Risk & Alerts (최근 원인분석)": "Process Risk & Alerts (Recent Root Cause)",
    "설비/공정 텔레메트리": "Equipment/Process Telemetry",
    "설비/공정 텔레메트리 (Phase 3 예정 — 챔버 온도, 로봇 상태 등 합성 장비 로그 연동 후 채워짐)":
      "Equipment/Process Telemetry (Phase 3 planned — populated once synthetic equipment logs like chamber temperature and robot status are wired up)",
    "공정 위험 지표": "Process Risk Indicators",
    "공정 위험 지표 (Phase 3 예정 — 실시간 이상탐지 알림)": "Process Risk Indicators (Phase 3 planned — real-time anomaly alerts)",
    "공정 단계 타임라인": "Process Stage Timeline",
    "공정 단계 타임라인 (Phase 3 예정 — SECS/GEM 합성 로그 기반 공정 진행률)":
      "Process Stage Timeline (Phase 3 planned — SECS/GEM synthetic-log-based process progress)",
    "Lot 선택 / 패턴별 웨이퍼 수 / Lot Trend": "Lot Selection / Wafer Count by Pattern / Lot Trend",
    "Composite 웨이퍼맵 히트맵 (패턴별 평균)": "Composite Wafer Map Heatmap (Average by Pattern)",
    "전체 웨이퍼 데이터": "All Wafer Data",
    "모델 임계값 슬라이더": "Model Threshold Slider",
    "원인분석 (최근)": "Root Cause Analysis (Recent)",
    "파이프라인 실행": "Pipeline Run",
    "결함-센서 상관관계 (드래그해서 탐색)": "Defect-Sensor Correlation (drag to explore)",
    "센서 데이터 (현재 웨이퍼)": "Sensor Data (Current Wafer)",
    "Lot 선택": "Select Lot",
    "패턴별 웨이퍼 수 ": "Wafer Count by Pattern ",
    "모델 임계값 (Model Threshold): ": "Model Threshold: ",
    "랜덤 샘플 실행": "Run Random Sample",
    "샘플링/분류": "Sample / Classify",
    "결함 설명": "Describe Defect",
    "원인 분석": "Root Cause",
    "심각도 판정": "Assess Severity",
    "해결책 제안": "Suggest Recipe",
    "X축 센서를 여기로 드래그": "Drag X-axis sensor here",
    "Y축 센서를 여기로 드래그": "Drag Y-axis sensor here",
    "센서 2개를 왼쪽 목록에서 드래그해서 산점도를 그려보세요": "Drag 2 sensors from the list on the left to plot them",
    "센서": "Sensor",
    "값": "Value",
    "기준평균": "Baseline Mean",
    "편차(σ)": "Deviation (σ)",
    "심각도": "Severity",
    "원인 가설": "Root Cause Hypothesis",
    "권장 조치": "Recommended Action",
    "로딩 중...": "Loading...",
    "불러오는 중...": "Loading...",
    "분석 중...": "Analyzing...",
    "요청 전송 중...": "Sending request...",
    "이미 실행 중입니다": "Already running",
    "데이터 없음": "No data",
    "lot 검색 (예: lot123)": "Search lot (e.g. lot123)",
    "센서 검색 (예: feature_162)": "Search sensor (e.g. feature_162)"
  };

  function translateFragment(raw) {
    var trimmed = raw.trim();
    if (!trimmed) return null;
    var lead = raw.slice(0, raw.length - raw.replace(/^\s+/, "").length);
    var trail = raw.slice(raw.replace(/\s+$/, "").length);
    var out = null;
    if (Object.prototype.hasOwnProperty.call(STATIC_DICT, trimmed)) {
      out = STATIC_DICT[trimmed];
    }
    return out === null ? null : lead + out + trail;
  }

  function applyTranslations() {
    var lang = getLang();
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        var tag = n.parentNode && n.parentNode.nodeName;
        if (tag === "SCRIPT" || tag === "STYLE") return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var node,
      textNodes = [];
    while ((node = walker.nextNode())) textNodes.push(node);
    textNodes.forEach(function (n) {
      if (lang === "en") {
        if (!koMap.has(n)) {
          var translated = translateFragment(n.nodeValue);
          if (translated !== null) {
            koMap.set(n, n.nodeValue);
            n.nodeValue = translated;
          }
        }
      } else if (koMap.has(n)) {
        n.nodeValue = koMap.get(n);
        koMap.delete(n);
      }
    });

    ["placeholder", "aria-label", "title"].forEach(function (attr) {
      document.querySelectorAll("[" + attr + "]").forEach(function (el) {
        if (el.id === "fascope-menu-toggle" || el.id === "fascope-lang-toggle") return;
        var markAttr = "data-fascope-ko-" + attr;
        if (lang === "en") {
          if (!el.hasAttribute(markAttr)) {
            var original = el.getAttribute(attr);
            var translated = translateFragment(original);
            if (translated !== null) {
              el.setAttribute(markAttr, original);
              el.setAttribute(attr, translated);
            }
          }
        } else if (el.hasAttribute(markAttr)) {
          el.setAttribute(attr, el.getAttribute(markAttr));
          el.removeAttribute(markAttr);
        }
      });
    });
  }
```

- [ ] **Step 2: Verify bind mount, then validate and reload**

```bash
docker exec daol-fascope-waferscope-nginx md5sum /etc/nginx/custom/fascope-lang.js
md5sum nginx/fascope-lang.js
# if mismatched: docker restart daol-fascope-waferscope-nginx, then recheck
docker exec daol-fascope-waferscope-nginx nginx -t
docker exec daol-fascope-waferscope-nginx nginx -s reload
```

- [ ] **Step 3: curl smoke check**

```bash
curl -s http://localhost:8090/assets/fascope-lang.js | grep -c 'Defect Detection Overview'
```
Expected: ≥ 1.

- [ ] **Step 4: Manual browser check**

Open Wafer Overview and Wafer Detail with the language toggle set to `EN`. Confirm widget titles and static labels listed in `STATIC_DICT` above appear in English (spot-check "Wafer Yield Map (Recent Wafer)", "Model Threshold Slider", "All Wafer Data", the pipeline step labels, the sensor table headers, the lot/sensor search placeholders). Toggle back to `한` and confirm exact Korean text is restored.

- [ ] **Step 5: Commit**

```bash
git add nginx/fascope-lang.js
git commit -m "$(cat <<'EOF'
feat: translate static WaferScope widget text for EN language mode

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Dynamic (interpolated) message translation

**Files:**
- Modify: `nginx/fascope-lang.js`

**Interfaces:**
- Consumes: `translateFragment(raw)` from Task 3 (its external signature is unchanged; its internal matching logic gets a regex fallback).
- Produces: `DYNAMIC_RULES` (ordered array of `[RegExp, String]` pairs).

- [ ] **Step 1: Add `DYNAMIC_RULES` and extend `translateFragment` to consult it**

In `nginx/fascope-lang.js`, find the `translateFragment` function added in Task 3:

```javascript
  function translateFragment(raw) {
    var trimmed = raw.trim();
    if (!trimmed) return null;
    var lead = raw.slice(0, raw.length - raw.replace(/^\s+/, "").length);
    var trail = raw.slice(raw.replace(/\s+$/, "").length);
    var out = null;
    if (Object.prototype.hasOwnProperty.call(STATIC_DICT, trimmed)) {
      out = STATIC_DICT[trimmed];
    }
    return out === null ? null : lead + out + trail;
  }
```

Replace it with:

```javascript
  var DYNAMIC_RULES = [
    [/^(\d+) \/ (\d+) 웨이퍼 로드됨$/, "$1 / $2 wafers loaded"],
    [/ 연결 실패 — 서버 가동 여부 확인 필요$/, " connection failed — check whether the server is running"],
    [/ 연결 실패$/, " connection failed"],
    [/^요청 실패 \((.+)\)$/, "request failed ($1)"],
    [/^(.+) vs (.+) \((\d+)개 웨이퍼, 클래스당 최대 200개 샘플\)$/, "$1 vs $2 ($3 wafers, max 200 samples per class)"],
    [/^(.+) 소유 센서 (\d+)개 \(wafer (.+)\)$/, "$2 sensors owned by $1 (wafer $3)"],
    [/^정상 범위 \(\|σ\|>(.+) 센서 없음\)$/, "normal range (no sensors with |σ|>$1)"],
    [/^⚠ (\d+)개 센서 임계치\(\|σ\|>(.+)\) 초과$/, "⚠ $1 sensors over threshold (|σ|>$2)"],
    [/^실패 \((.+?)\):\s*(.*)$/, "failed ($1): $2"],
    [/^(\d+)개 lot 중 상위 50개 표시 \(검색으로 좁히기\)$/, "$1 lots found — showing top 50 (narrow your search)"],
    [/\(값 ([^)]+)\)/, "(value $1)"]
  ];

  function translateFragment(raw) {
    var trimmed = raw.trim();
    if (!trimmed) return null;
    var lead = raw.slice(0, raw.length - raw.replace(/^\s+/, "").length);
    var trail = raw.slice(raw.replace(/\s+$/, "").length);
    var out = null;
    if (Object.prototype.hasOwnProperty.call(STATIC_DICT, trimmed)) {
      out = STATIC_DICT[trimmed];
    } else {
      for (var i = 0; i < DYNAMIC_RULES.length; i++) {
        if (DYNAMIC_RULES[i][0].test(trimmed)) {
          out = trimmed.replace(DYNAMIC_RULES[i][0], DYNAMIC_RULES[i][1]);
          break;
        }
      }
    }
    return out === null ? null : lead + out + trail;
  }
```

- [ ] **Step 2: Verify bind mount, then validate and reload**

```bash
docker exec daol-fascope-waferscope-nginx md5sum /etc/nginx/custom/fascope-lang.js
md5sum nginx/fascope-lang.js
# if mismatched: docker restart daol-fascope-waferscope-nginx, then recheck
docker exec daol-fascope-waferscope-nginx nginx -t
docker exec daol-fascope-waferscope-nginx nginx -s reload
```

- [ ] **Step 3: curl smoke check**

```bash
curl -s http://localhost:8090/assets/fascope-lang.js | grep -c 'wafers loaded'
```
Expected: ≥ 1.

- [ ] **Step 4: Manual browser check**

With the language toggle set to `EN`:
- On "Wafer Detail", click "Run Random Sample" and watch it move through stages; confirm status text reads in English.
- On "Wafer Overview", drag two sensors onto the correlation scatter widget's X/Y drop zones; confirm the resulting status line reads like "feature_12 vs feature_88 (37 wafers, max 200 samples per class)".
- In the Lot selector search box, check the "showing top 50" hint text if it appears; confirm it reads in English.
- Toggle back to `한` and spot-check that dynamic messages revert to Korean on their next update.

- [ ] **Step 5: Commit**

```bash
git add nginx/fascope-lang.js
git commit -m "$(cat <<'EOF'
feat: translate dynamic interpolated status messages for EN mode

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: End-to-end acceptance walkthrough

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Fresh-session walkthrough**

In a private/incognito browser window (clean `localStorage`), open `http://<host>:8090`, log in, and confirm the site loads entirely in Korean by default.

- [ ] **Step 2: Full EN pass**

Click the language toggle on Wafer Overview. Visit every widget on both Wafer Overview and Wafer Detail and confirm every string catalogued in the design spec's "Static dictionary" and "Dynamic regex rules" sections is in English. Note any remaining Korean strings (expected: ThingsBoard's own native sidenav menu item labels — out of scope unless found Korean, per the design spec).

- [ ] **Step 3: Round-trip check**

Toggle back to `한`. Reload the page. Confirm the preference persisted and every widget shows its original Korean text, byte-for-byte, with no leftover English fragments or broken layout.

- [ ] **Step 4: Report findings**

If Step 2 found native ThingsBoard chrome still in Korean and the user wants it covered, that's a follow-up (add those strings to `STATIC_DICT`), not a plan revision.

No commit for this task.

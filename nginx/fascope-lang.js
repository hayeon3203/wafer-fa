(function () {
  var L = ["개체", "Edge management"];
  var D = ["Wafer Overview", "Wafer Detail"];
  var KEY = "fascopeMenuCollapsed";
  var LANG_KEY = "fascopeLang";
  var koMap = new WeakMap();

  function getLang() {
    return localStorage.getItem(LANG_KEY) === "en" ? "en" : "ko";
  }

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

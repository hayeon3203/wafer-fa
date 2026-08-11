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

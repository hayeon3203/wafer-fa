"""One-time setup: create the daol-fascope custom widget types + two dashboards in
ThingsBoard -- "Wafer Overview" (control-room style, mirrors data/dashboard_sample2.png)
and "Wafer Detail" (lot/pattern drill-down, mirrors data/dashboard_sample.png).
Re-running creates duplicates (no upsert) -- only meant to be run once against a
fresh tenant.
"""
import json
import os
import sys
import uuid

import requests

THINGSBOARD_URL = os.environ.get("THINGSBOARD_URL", "http://localhost:8082")
TB_USERNAME = os.environ["THINGSBOARD_ADMIN_USERNAME"]
TB_PASSWORD = os.environ["THINGSBOARD_ADMIN_PASSWORD"]
DEVICE_ID = os.environ["THINGSBOARD_DEVICE_ID"]


def login():
    resp = requests.post(
        f"{THINGSBOARD_URL}/api/auth/login",
        json={"username": TB_USERNAME, "password": TB_PASSWORD},
    )
    resp.raise_for_status()
    return resp.json()["token"]


def create_widget_type(token, name, description, template_html, template_css,
                        controller_script, size_x=8, size_y=5):
    headers = {"X-Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "name": name,
        "description": description,
        "descriptor": {
            "type": "latest",
            "sizeX": size_x,
            "sizeY": size_y,
            "resources": [],
            "templateHtml": template_html,
            "templateCss": template_css,
            "controllerScript": controller_script,
            "settingsSchema": "{}",
            "dataKeySettingsSchema": "{}",
            "defaultConfig": json.dumps(
                {"datasources": [], "showTitle": True, "title": name, "settings": {}}
            ),
        },
    }
    resp = requests.post(f"{THINGSBOARD_URL}/api/widgetType", headers=headers, json=body)
    resp.raise_for_status()
    # GET /api/widgetType?fqn=... requires a "system."/"tenant." scope prefix on
    # the fqn or it 400s with "Invalid fqn!" -- the bare fqn returned by this API
    # is not by itself a valid typeFullFqn for a dashboard widget reference.
    return f"tenant.{resp.json()['fqn']}"


# ---------------------------------------------------------------------------
# Custom widget: Lot Panel (search + list only; selection feeds Lot Detail widget
# via a shared in-widget click -> both widgets query the SAME lot_pattern_counts
# attribute independently, so this one is presentational selection + everything
# below reacts through its own copy of the data using window-level state).
# ---------------------------------------------------------------------------
LOT_ANALYSIS_HTML = """
<div class="lot-wrap">
  <div class="lot-panel">
    <div class="lot-title">Lot 선택</div>
    <input type="text" class="lot-search" placeholder="lot 검색 (예: lot123)" />
    <div class="lot-list"></div>
  </div>
  <div class="lot-detail">
    <div class="lot-detail-title">패턴별 웨이퍼 수 <span class="lot-detail-name"></span></div>
    <table class="lot-table"><tbody></tbody></table>
    <div class="lot-trend-title">Lot Trend</div>
    <div class="lot-trend"></div>
  </div>
</div>
"""

LOT_ANALYSIS_CSS = """
.lot-wrap { display: flex; height: 100%; font-family: Roboto, sans-serif; box-sizing: border-box; }
.lot-panel { width: 220px; flex-shrink: 0; border-right: 1px solid #eee; padding: 8px; box-sizing: border-box; display: flex; flex-direction: column; }
.lot-title, .lot-detail-title, .lot-trend-title { font-weight: 600; font-size: 13px; color: #555; margin-bottom: 6px; text-transform: uppercase; }
.lot-search { width: 100%; box-sizing: border-box; padding: 6px; margin-bottom: 8px; border: 1px solid #ddd; border-radius: 4px; }
.lot-list { overflow-y: auto; flex: 1; }
.lot-item { padding: 6px 8px; cursor: pointer; border-radius: 4px; font-size: 13px; }
.lot-item:hover { background: #f0f4ff; }
.lot-item.selected { background: #3f51b5; color: white; }
.lot-hint { color: #999; font-size: 12px; padding: 6px; }
.lot-detail { flex: 1; padding: 8px 16px; overflow-y: auto; box-sizing: border-box; }
.lot-detail-name { font-weight: 400; color: #3f51b5; text-transform: none; }
.lot-table { width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 13px; }
.lot-table td { padding: 4px 8px; border-bottom: 1px solid #f0f0f0; }
.lot-trend-row { display: flex; align-items: center; margin-bottom: 6px; font-size: 12px; }
.lot-trend-label { width: 80px; flex-shrink: 0; }
.lot-trend-bar-bg { flex: 1; background: #f0f0f0; border-radius: 3px; margin: 0 8px; height: 14px; }
.lot-trend-bar { background: #ff9800; height: 100%; border-radius: 3px; }
.lot-trend-count { width: 30px; text-align: right; }
"""

LOT_ANALYSIS_JS = """
self.onInit = function() {
    self.ctx.lotCounts = {};
    self.ctx.selectedLot = null;
    render();
};

self.onDataUpdated = function() {
    parseData();
    render();
};

function parseData() {
    if (self.ctx.data && self.ctx.data[0] && self.ctx.data[0].data && self.ctx.data[0].data.length) {
        var latest = self.ctx.data[0].data[self.ctx.data[0].data.length - 1];
        try {
            self.ctx.lotCounts = JSON.parse(latest[1]);
        } catch (e) {
            self.ctx.lotCounts = {};
        }
    }
}

function render() {
    var container = self.ctx.$container[0];
    if (!container) return;
    var listEl = container.querySelector('.lot-list');
    var searchEl = container.querySelector('.lot-search');
    var tableBody = container.querySelector('.lot-table tbody');
    var trendEl = container.querySelector('.lot-trend');
    var nameEl = container.querySelector('.lot-detail-name');

    var lots = Object.keys(self.ctx.lotCounts).sort();

    function renderList(filter) {
        listEl.innerHTML = '';
        var matches = lots.filter(function(l) {
            return !filter || l.toLowerCase().indexOf(filter.toLowerCase()) >= 0;
        });
        if (!filter) {
            var hint = document.createElement('div');
            hint.className = 'lot-hint';
            hint.textContent = matches.length + '개 lot 중 상위 50개 표시 (검색으로 좁히기)';
            listEl.appendChild(hint);
            matches = matches.slice(0, 50);
        } else {
            matches = matches.slice(0, 200);
        }
        matches.forEach(function(lot) {
            var item = document.createElement('div');
            item.className = 'lot-item' + (lot === self.ctx.selectedLot ? ' selected' : '');
            item.textContent = lot;
            item.onclick = function() {
                self.ctx.selectedLot = lot;
                renderList(searchEl.value);
                renderDetail(lot);
            };
            listEl.appendChild(item);
        });
    }

    function renderDetail(lot) {
        nameEl.textContent = lot ? '- ' + lot : '';
        var counts = self.ctx.lotCounts[lot] || {};
        var entries = Object.keys(counts)
            .map(function(k) { return [k, counts[k]]; })
            .filter(function(e) { return e[1] > 0; })
            .sort(function(a, b) { return b[1] - a[1]; });
        tableBody.innerHTML = '';
        entries.forEach(function(e) {
            var tr = document.createElement('tr');
            tr.innerHTML = '<td>' + e[0] + '</td><td>' + e[1] + '</td>';
            tableBody.appendChild(tr);
        });
        var maxCount = entries.length ? entries[0][1] : 1;
        trendEl.innerHTML = '';
        entries.forEach(function(e) {
            var row = document.createElement('div');
            row.className = 'lot-trend-row';
            var pct = Math.round((e[1] / maxCount) * 100);
            row.innerHTML = '<span class="lot-trend-label">' + e[0] + '</span>' +
                '<div class="lot-trend-bar-bg"><div class="lot-trend-bar" style="width:' + pct + '%"></div></div>' +
                '<span class="lot-trend-count">' + e[1] + '</span>';
            trendEl.appendChild(row);
        });
    }

    searchEl.oninput = function() { renderList(searchEl.value); };
    renderList('');
    if (self.ctx.selectedLot && self.ctx.lotCounts[self.ctx.selectedLot]) {
        renderDetail(self.ctx.selectedLot);
    } else if (lots.length) {
        self.ctx.selectedLot = lots[0];
        renderDetail(lots[0]);
    }
}

self.onResize = function() {};
self.onDestroy = function() {};
"""

SLIDER_HTML = """
<div class="tb-slider-wrap">
  <div class="tb-slider-label">모델 임계값 (Model Threshold): <span class="tb-slider-value">-</span></div>
  <input type="range" class="tb-slider-input" min="0" max="1" step="0.01" />
</div>
"""

SLIDER_CSS = """
.tb-slider-wrap { display: flex; flex-direction: column; justify-content: center; height: 100%; padding: 16px; box-sizing: border-box; font-family: Roboto, sans-serif; }
.tb-slider-label { margin-bottom: 12px; font-size: 15px; color: #333; }
.tb-slider-value { font-weight: 600; }
.tb-slider-input { width: 100%; }
"""

SLIDER_JS = """
self.onInit = function() {
    var $injector = self.ctx.$scope.$injector;
    var attributeService = $injector.get(self.ctx.servicesMap.get('attributeService'));
    var container = self.ctx.$container[0];
    var input = container.querySelector('.tb-slider-input');
    var valueLabel = container.querySelector('.tb-slider-value');

    function currentEntityId() {
        var ds = self.ctx.datasources && self.ctx.datasources[0];
        return ds ? { entityType: ds.entityType, id: ds.entityId } : null;
    }

    input.addEventListener('input', function() {
        valueLabel.textContent = parseFloat(input.value).toFixed(2);
    });

    input.addEventListener('change', function() {
        var val = parseFloat(input.value);
        valueLabel.textContent = val.toFixed(2);
        var entityId = currentEntityId();
        if (entityId) {
            attributeService.saveEntityAttributes(entityId, 'SERVER_SCOPE', [
                { key: 'confidence_threshold', value: val }
            ]).subscribe(function() {});
        }
    });

    self.onDataUpdated();
};

self.onDataUpdated = function() {
    var container = self.ctx.$container[0];
    if (!container) return;
    var input = container.querySelector('.tb-slider-input');
    var valueLabel = container.querySelector('.tb-slider-value');
    if (self.ctx.data && self.ctx.data[0] && self.ctx.data[0].data && self.ctx.data[0].data.length) {
        var latest = self.ctx.data[0].data[self.ctx.data[0].data.length - 1];
        var val = parseFloat(latest[1]);
        if (!isNaN(val)) {
            input.value = val;
            valueLabel.textContent = val.toFixed(2);
        }
    }
};

self.onResize = function() {};
self.onDestroy = function() {};
"""

CLASS_OVERVIEW_HTML = """<div class="co-wrap"><div class="co-bars"></div></div>"""

CLASS_OVERVIEW_CSS = """
.co-wrap { height: 100%; padding: 8px 16px; box-sizing: border-box; overflow-y: auto; font-family: Roboto, sans-serif; }
.co-row { display: flex; align-items: center; margin-bottom: 8px; font-size: 12px; }
.co-label { width: 70px; flex-shrink: 0; }
.co-bar-bg { flex: 1; background: #f0f0f0; border-radius: 3px; margin: 0 8px; height: 14px; }
.co-bar { background: #e53935; height: 100%; border-radius: 3px; }
.co-count { width: 46px; text-align: right; }
"""

CLASS_OVERVIEW_JS = """
self.onInit = function() { render(); };
self.onDataUpdated = function() { render(); };

function render() {
    var container = self.ctx.$container[0];
    if (!container) return;
    var barsEl = container.querySelector('.co-bars');
    var lotCounts = {};
    if (self.ctx.data && self.ctx.data[0] && self.ctx.data[0].data && self.ctx.data[0].data.length) {
        var latest = self.ctx.data[0].data[self.ctx.data[0].data.length - 1];
        try { lotCounts = JSON.parse(latest[1]); } catch (e) { lotCounts = {}; }
    }
    var totals = {};
    Object.keys(lotCounts).forEach(function(lot) {
        var counts = lotCounts[lot];
        Object.keys(counts).forEach(function(cls) {
            totals[cls] = (totals[cls] || 0) + counts[cls];
        });
    });
    var entries = Object.keys(totals).map(function(k) { return [k, totals[k]]; })
        .sort(function(a, b) { return b[1] - a[1]; });
    var maxCount = entries.length ? entries[0][1] : 1;
    barsEl.innerHTML = '';
    entries.forEach(function(e) {
        var pct = Math.round((e[1] / maxCount) * 100);
        var row = document.createElement('div');
        row.className = 'co-row';
        row.innerHTML = '<span class="co-label">' + e[0] + '</span>' +
            '<div class="co-bar-bg"><div class="co-bar" style="width:' + pct + '%"></div></div>' +
            '<span class="co-count">' + e[1] + '</span>';
        barsEl.appendChild(row);
    });
}

self.onResize = function() {};
self.onDestroy = function() {};
"""

WAFER_GALLERY_HTML = """
<div class="wg-scroll">
  <div class="wg-status"></div>
  <div class="wg-wrap"></div>
  <div class="wg-sentinel"></div>
</div>
"""

WAFER_GALLERY_CSS = """
.wg-scroll { height: 100%; overflow-y: auto; box-sizing: border-box; font-family: Roboto, sans-serif; }
.wg-status { padding: 6px 10px; font-size: 11px; color: #999; }
.wg-wrap { display: flex; flex-wrap: wrap; gap: 10px; padding: 0 10px 10px; }
.wg-item { width: 90px; text-align: center; }
.wg-item img { width: 80px; height: 80px; border: 1px solid #eee; border-radius: 4px; }
.wg-cap { font-size: 11px; color: #555; margin-top: 4px; }
.wg-sub { color: #999; }
.wg-sentinel { height: 1px; }
"""

# Fetches from wafer_browser_server.py (stdlib http.server, run separately --
# see `python -m daol_fascope.wafer_browser_server`). The full manifest (~173k
# wafers, all classes including "none") is way past what fits in one TB
# device attribute, so this widget paginates against that API on scroll
# instead of reading data through self.ctx.data at all.
WAFER_GALLERY_JS = """
var API_PORT = 8091;
var PAGE_SIZE = 40;

self.onInit = function() {
    self.ctx.wgOffset = 0;
    self.ctx.wgTotal = null;
    self.ctx.wgLoading = false;
    var container = self.ctx.$container[0];
    container.querySelector('.wg-scroll').addEventListener('scroll', onScroll);
    loadMore();
};

function apiBase() {
    return 'http://' + window.location.hostname + ':' + API_PORT;
}

function onScroll(e) {
    var el = e.target;
    if (el.scrollTop + el.clientHeight > el.scrollHeight - 200) {
        loadMore();
    }
}

function loadMore() {
    if (self.ctx.wgLoading) return;
    if (self.ctx.wgTotal !== null && self.ctx.wgOffset >= self.ctx.wgTotal) return;
    self.ctx.wgLoading = true;
    var container = self.ctx.$container[0];
    var statusEl = container.querySelector('.wg-status');
    var wrapEl = container.querySelector('.wg-wrap');
    statusEl.textContent = '로딩 중...';

    var url = apiBase() + '/api/wafers?offset=' + self.ctx.wgOffset + '&limit=' + PAGE_SIZE;
    fetch(url).then(function(r) { return r.json(); }).then(function(data) {
        self.ctx.wgTotal = data.total;
        self.ctx.wgOffset += data.items.length;
        data.items.forEach(function(s) {
            var item = document.createElement('div');
            item.className = 'wg-item';
            item.innerHTML = '<img src="data:image/png;base64,' + s.image + '" />' +
                '<div class="wg-cap">' + s.label + '<br/><span class="wg-sub">' + s.lot_id + ' #' + s.wafer_index + '</span></div>';
            wrapEl.appendChild(item);
        });
        statusEl.textContent = self.ctx.wgOffset + ' / ' + data.total + ' 웨이퍼 로드됨';
        self.ctx.wgLoading = false;
        if (data.items.length === 0) return;
    }).catch(function(err) {
        statusEl.textContent = 'wafer_browser_server(:' + API_PORT + ') 연결 실패 — 서버 가동 여부 확인 필요';
        self.ctx.wgLoading = false;
    });
}

self.onDataUpdated = function() {};
self.onResize = function() {};
self.onDestroy = function() {};
"""

# Button + 5-box progress bar for wafer_predict_server.py (:8092, run separately
# -- see `python -m daol_fascope.wafer_predict_server`). POSTs /api/predict on click
# (fire-and-forget, server responds 202/409 immediately) and colors the 5 boxes
# purely from the latest pipeline_stage/pipeline_stage_error_node telemetry --
# no other source of truth. See docs/adr/0005.
PIPELINE_PROGRESS_HTML = """
<div class="pp-wrap">
  <button class="pp-run-btn">랜덤 샘플 실행</button>
  <div class="pp-status"></div>
  <div class="pp-steps">
    <div class="pp-step" data-stage="classify">샘플링/분류</div>
    <div class="pp-step" data-stage="describe">결함 설명</div>
    <div class="pp-step" data-stage="root_cause">원인 분석</div>
    <div class="pp-step" data-stage="severity">심각도 판정</div>
    <div class="pp-step" data-stage="recipe">해결책 제안</div>
  </div>
</div>
"""

PIPELINE_PROGRESS_CSS = """
.pp-wrap { display: flex; align-items: center; height: 100%; padding: 0 16px; box-sizing: border-box; font-family: Roboto, sans-serif; gap: 16px; }
.pp-run-btn { flex-shrink: 0; padding: 10px 16px; border-radius: 4px; border: none; background: #3f51b5; color: white; font-size: 13px; cursor: pointer; }
.pp-run-btn:disabled { opacity: 0.5; cursor: default; }
.pp-status { flex-shrink: 0; width: 160px; font-size: 12px; color: #999; }
.pp-steps { flex: 1; display: flex; gap: 8px; }
.pp-step { flex: 1; text-align: center; padding: 10px 4px; border-radius: 4px; font-size: 12px; border: 1px solid #ddd; background: white; color: #bbb; transition: background 0.3s, color 0.3s; }
.pp-step.pp-done { background: #e0e0e0; color: #888; border-color: #e0e0e0; }
.pp-step.pp-current { background: #ff9800; color: white; border-color: #ff9800; font-weight: 600; }
.pp-step.pp-error { background: #e53935; color: white; border-color: #e53935; font-weight: 600; }
"""

PIPELINE_PROGRESS_JS = """
var STAGES = ['classify', 'describe', 'root_cause', 'severity', 'recipe'];
var API_PORT = 8092;

function apiBase() {
    return 'http://' + window.location.hostname + ':' + API_PORT;
}

self.onInit = function() {
    var container = self.ctx.$container[0];
    var btn = container.querySelector('.pp-run-btn');
    var statusEl = container.querySelector('.pp-status');
    btn.addEventListener('click', function() {
        btn.disabled = true;
        statusEl.textContent = '요청 전송 중...';
        fetch(apiBase() + '/api/predict', { method: 'POST' }).then(function(resp) {
            if (resp.status === 202) {
                statusEl.textContent = '';
            } else if (resp.status === 409) {
                statusEl.textContent = '이미 실행 중입니다';
            } else {
                statusEl.textContent = '요청 실패 (' + resp.status + ')';
            }
        }).catch(function() {
            statusEl.textContent = 'wafer_predict_server(:' + API_PORT + ') 연결 실패';
        }).then(function() {
            btn.disabled = false;
        });
    });
    self.onDataUpdated();
};

self.onDataUpdated = function() {
    var container = self.ctx.$container[0];
    if (!container) return;
    if (!(self.ctx.data && self.ctx.data[0] && self.ctx.data[0].data && self.ctx.data[0].data.length)) return;

    var stage = self.ctx.data[0].data[self.ctx.data[0].data.length - 1][1];
    var errorNode = null;
    if (self.ctx.data[1] && self.ctx.data[1].data && self.ctx.data[1].data.length) {
        errorNode = self.ctx.data[1].data[self.ctx.data[1].data.length - 1][1];
    }

    var boundaryIndex = -1;
    if (stage === 'error') {
        boundaryIndex = STAGES.indexOf(errorNode);
    } else if (stage !== 'idle' && stage !== 'done') {
        boundaryIndex = STAGES.indexOf(stage);
    }

    container.querySelectorAll('.pp-step').forEach(function(el) {
        var idx = STAGES.indexOf(el.getAttribute('data-stage'));
        el.classList.remove('pp-done', 'pp-current', 'pp-pending', 'pp-error');
        if (stage === 'done') {
            el.classList.add('pp-done');
        } else if (stage === 'idle') {
            el.classList.add('pp-pending');
        } else if (stage === 'error' && idx === boundaryIndex) {
            el.classList.add('pp-error');
        } else if (idx < boundaryIndex) {
            el.classList.add('pp-done');
        } else if (idx === boundaryIndex) {
            el.classList.add('pp-current');
        } else {
            el.classList.add('pp-pending');
        }
    });
};

self.onResize = function() {};
self.onDestroy = function() {};
"""


def data_key(name, key_type="timeseries", label=None, extra=None):
    dk = {"name": name, "type": key_type, "label": label or name, "settings": {}}
    if extra:
        dk.update(extra)
    return dk


def entity_datasource(alias_id, keys):
    return {"type": "entity", "name": None, "entityAliasId": alias_id, "dataKeys": keys}


def widget(type_full_fqn, widget_type, size_x, size_y, row, col, config):
    wid = str(uuid.uuid4())
    return wid, {
        "typeFullFqn": type_full_fqn,
        "type": widget_type,
        "sizeX": size_x,
        "sizeY": size_y,
        "row": row,
        "col": col,
        "config": config,
        "id": wid,
    }


def make_dashboard(title, alias_id, widgets):
    layout = {wid: {"sizeX": w["sizeX"], "sizeY": w["sizeY"], "row": w["row"], "col": w["col"]}
              for wid, w in widgets.items()}
    return {
        "title": title,
        "configuration": {
            "widgets": widgets,
            "states": {
                "default": {
                    "name": title,
                    "root": True,
                    "layouts": {
                        "main": {
                            "widgets": layout,
                            "gridSettings": {"backgroundColor": "#fff", "columns": 24, "margin": 10},
                        }
                    },
                }
            },
            "entityAliases": {
                alias_id: {
                    "id": alias_id,
                    "alias": "Daol FAScope Pipeline Device",
                    "filter": {
                        "type": "singleEntity",
                        "singleEntity": {"entityType": "DEVICE", "id": DEVICE_ID},
                        "resolveMultiple": False,
                    },
                }
            },
            "settings": {},
        },
    }


def save_dashboard(token, dashboard):
    headers = {"X-Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(f"{THINGSBOARD_URL}/api/dashboard", headers=headers, json=dashboard)
    resp.raise_for_status()
    return resp.json()


def build_overview_dashboard(alias_id, class_overview_fqn):
    widgets = {}

    placeholder_css = (
        ".ph { display:flex; align-items:center; justify-content:center; height:100%;"
        " font-size:14px; color:#999; font-family: Roboto, sans-serif; text-align:center;"
        " padding:16px; box-sizing:border-box; }"
    )

    def placeholder(text, size_x, size_y, row, col):
        return widget(
            "system.cards.html_card", "static", size_x, size_y, row, col,
            {
                "datasources": [], "showTitle": True, "title": text.split(" (")[0], "settings": {
                    "cardCss": placeholder_css,
                    "cardHtml": f"<div class='ph'>{text}</div>",
                },
            },
        )

    wid, w = widget(
        class_overview_fqn, "latest", 6, 10, 0, 0,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("lot_pattern_counts", "attribute", "lot_pattern_counts"),
            ])],
            "title": "결함 검출 개요 (Defect Detection)", "showTitle": True, "settings": {},
        },
    )
    widgets[wid] = w

    wid, w = widget(
        "system.cards.html_value_card", "latest", 12, 10, 0, 6,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("wafer_image", "timeseries", "wafer_image"),
                data_key("defect_class", "timeseries", "defect_class"),
                data_key("confidence", "timeseries", "confidence"),
                data_key("die_yield_pct", "timeseries", "die_yield_pct"),
                data_key("lot_id", "timeseries", "lot_id"),
            ])],
            "title": "Wafer Yield Map (최근 웨이퍼)", "showTitle": True,
            "settings": {
                "cardCss": (
                    ".yield-wrap { display:flex; align-items:center; justify-content:space-around;"
                    " height:100%; font-family: Roboto, sans-serif; padding:12px; box-sizing:border-box; }\n"
                    ".yield-wrap img { max-height: 85%; border-radius: 50%; border: 4px solid #f0f0f0; }\n"
                    ".yield-stat { text-align:center; }\n"
                    ".yield-stat .big { font-size: 42px; font-weight: 300; color:#2e7d32; }\n"
                    ".yield-stat .sub { font-size: 13px; color:#888; margin-top:6px; }"
                ),
                "cardHtml": (
                    "<div class='yield-wrap'>"
                    "<img src='data:image/png;base64,${wafer_image}' />"
                    "<div class='yield-stat'><div class='big'>${die_yield_pct:1}%</div>"
                    "<div class='sub'>Composite Yield</div>"
                    "<div class='sub'>${defect_class} (${confidence:2}) / lot ${lot_id}</div></div>"
                    "</div>"
                ),
            },
        },
    )
    widgets[wid] = w

    wid, w = widget(
        "system.cards.html_value_card", "latest", 6, 10, 0, 18,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("severity", "timeseries", "severity"),
                data_key("root_cause", "timeseries", "root_cause"),
                data_key("recipe", "timeseries", "recipe"),
            ])],
            "title": "Process Risk & Alerts (최근 원인분석)", "showTitle": True,
            "settings": {
                "cardCss": (
                    ".pr { padding:12px; font-family: Roboto, sans-serif; font-size:13px; line-height:1.5; }\n"
                    ".pr h4 { margin: 10px 0 2px; font-size:12px; color:#888; text-transform:uppercase; }"
                ),
                "cardHtml": (
                    "<div class='pr'><h4>심각도</h4><p><b>${severity}</b></p>"
                    "<h4>원인 가설</h4><p>${root_cause}</p>"
                    "<h4>권장 조치</h4><p>${recipe}</p></div>"
                ),
            },
        },
    )
    widgets[wid] = w

    wid, w = placeholder(
        "설비/공정 텔레메트리 (Phase 3 예정 — 챔버 온도, 로봇 상태 등 합성 장비 로그 연동 후 채워짐)",
        6, 6, 10, 0,
    )
    widgets[wid] = w

    wid, w = placeholder(
        "공정 위험 지표 (Phase 3 예정 — 실시간 이상탐지 알림)",
        6, 6, 10, 18,
    )
    widgets[wid] = w

    wid, w = placeholder(
        "공정 단계 타임라인 (Phase 3 예정 — SECS/GEM 합성 로그 기반 공정 진행률)",
        12, 6, 10, 6,
    )
    widgets[wid] = w

    return make_dashboard("Wafer Overview", alias_id, widgets)


def build_detail_dashboard(alias_id, lot_analysis_fqn, slider_fqn, wafer_gallery_fqn):
    widgets = {}

    wid, w = widget(
        lot_analysis_fqn, "latest", 14, 9, 0, 0,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("lot_pattern_counts", "attribute", "lot_pattern_counts"),
            ])],
            "title": "Lot 선택 / 패턴별 웨이퍼 수 / Lot Trend", "showTitle": True, "settings": {},
        },
    )
    widgets[wid] = w

    composite_classes = ["Center", "Donut", "Edge-Loc", "Edge-Ring", "Loc",
                          "Random", "Scratch", "Near-full", "none"]
    composite_imgs = "".join(
        f"<div class='composite-item'><img src='data:image/png;base64,${{composite_{c.replace('-', '_')}}}' />"
        f"<div class='composite-label'>{c}</div></div>"
        for c in composite_classes
    )
    composite_keys = [
        data_key(f"composite_{c.replace('-', '_')}", "attribute", f"composite_{c.replace('-', '_')}")
        for c in composite_classes
    ]
    wid, w = widget(
        "system.cards.html_value_card", "latest", 19, 8, 9, 0,
        {
            "datasources": [entity_datasource(alias_id, composite_keys)],
            "title": "Composite 웨이퍼맵 히트맵 (패턴별 평균)", "showTitle": True,
            "settings": {
                "cardCss": (
                    ".grid { display:flex; flex-wrap:wrap; gap:10px; padding:10px; font-family: Roboto, sans-serif; }\n"
                    ".composite-item { width: 90px; text-align:center; }\n"
                    ".composite-item img { width: 80px; height: 80px; border-radius: 50%; }\n"
                    ".composite-label { font-size: 11px; color:#666; margin-top:4px; }"
                ),
                "cardHtml": f"<div class='grid'>{composite_imgs}</div>",
            },
        },
    )
    widgets[wid] = w

    wid, w = widget(
        wafer_gallery_fqn, "latest", 10, 9, 0, 14,
        {
            "datasources": [],
            "title": "전체 웨이퍼 데이터", "showTitle": True, "settings": {},
        },
    )
    widgets[wid] = w

    wid, w = widget(
        slider_fqn, "latest", 5, 4, 9, 19,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("confidence_threshold", "attribute", "confidence_threshold"),
            ])],
            "title": "모델 임계값 슬라이더", "showTitle": True, "settings": {},
        },
    )
    widgets[wid] = w

    wid, w = widget(
        "system.cards.html_value_card", "latest", 5, 4, 13, 19,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("description", "timeseries", "description"),
                data_key("severity", "timeseries", "severity"),
            ])],
            "title": "원인분석 (최근)", "showTitle": True,
            "settings": {
                "cardCss": ".rc2 { padding:10px; font-family: Roboto, sans-serif; font-size:12px; line-height:1.4; overflow-y:auto; height:100%; box-sizing:border-box; }",
                "cardHtml": "<div class='rc2'><b>${severity}</b><p>${description}</p></div>",
            },
        },
    )
    widgets[wid] = w

    return make_dashboard("Wafer Detail", alias_id, widgets)


def main():
    token = login()

    lot_analysis_fqn = create_widget_type(
        token, "Daol FAScope Lot Analysis", "Lot select + per-pattern count table + trend bars",
        LOT_ANALYSIS_HTML, LOT_ANALYSIS_CSS, LOT_ANALYSIS_JS, size_x=12, size_y=8,
    )
    slider_fqn = create_widget_type(
        token, "Daol FAScope Threshold Slider", "Writable model confidence threshold slider",
        SLIDER_HTML, SLIDER_CSS, SLIDER_JS, size_x=6, size_y=3,
    )
    class_overview_fqn = create_widget_type(
        token, "Daol FAScope Class Overview", "Global per-pattern defect counts, aggregated from lot_pattern_counts",
        CLASS_OVERVIEW_HTML, CLASS_OVERVIEW_CSS, CLASS_OVERVIEW_JS, size_x=6, size_y=10,
    )
    wafer_gallery_fqn = create_widget_type(
        token, "Daol FAScope Wafer Gallery", "Infinite-scroll grid over the full wafer dataset (all classes incl. none), paginated via wafer_browser_server.py",
        WAFER_GALLERY_HTML, WAFER_GALLERY_CSS, WAFER_GALLERY_JS, size_x=19, size_y=8,
    )

    alias_id = str(uuid.uuid4())

    overview = build_overview_dashboard(alias_id, class_overview_fqn)
    detail = build_detail_dashboard(alias_id, lot_analysis_fqn, slider_fqn, wafer_gallery_fqn)

    overview_result = save_dashboard(token, overview)
    detail_result = save_dashboard(token, detail)

    print("overview dashboard id:", overview_result["id"]["id"])
    print("detail dashboard id:", detail_result["id"]["id"])
    print("lot_analysis_fqn:", lot_analysis_fqn)
    print("slider_fqn:", slider_fqn)
    print("class_overview_fqn:", class_overview_fqn)
    print("wafer_gallery_fqn:", wafer_gallery_fqn)


def apply_pipeline_progress_widget():
    """Patch the live "Wafer Detail" dashboard in place: swap its "공정 단계
    타임라인" Phase 3 placeholder for the button + 5-node progress bar.

    Update-in-place (GET current config, edit one widget entry, POST the whole
    thing back with its existing "id") rather than recreate-from-scratch, so it
    doesn't clobber anything hand-edited in the TB UI since the original setup()
    run -- see Plans.md Phase 2.5.4 for why that already happened once here.

    Needs THINGSBOARD_ADMIN_USERNAME/PASSWORD for a *tenant admin* account
    (sysadmin's own login can log in fine but can't see tenant dashboards --
    GET /api/tenant/dashboards 302s to the login page for it). Tenant admin is
    admin@daol-fascope.local per Plans.md; password is stored outside this repo.
    """
    token = login()
    headers = {"X-Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = requests.get(f"{THINGSBOARD_URL}/api/tenant/dashboards?pageSize=50&page=0", headers=headers)
    resp.raise_for_status()
    match = next((d for d in resp.json()["data"] if d["title"] == "Wafer Detail"), None)
    if match is None:
        raise RuntimeError('no dashboard titled "Wafer Detail" found -- check the live title first')

    resp = requests.get(f"{THINGSBOARD_URL}/api/dashboard/{match['id']['id']}", headers=headers)
    resp.raise_for_status()
    dashboard = resp.json()

    widgets = dashboard["configuration"]["widgets"]
    target_id = next(
        (wid for wid, w in widgets.items() if w.get("config", {}).get("title") == "공정 단계 타임라인"),
        None,
    )
    if target_id is None:
        raise RuntimeError('no "공정 단계 타임라인" placeholder widget on "Wafer Detail" -- already replaced?')

    entity_alias_id = next(iter(dashboard["configuration"]["entityAliases"]))
    pipeline_progress_fqn = create_widget_type(
        token, "Daol FAScope Pipeline Progress",
        "Run button + 5-stage pipeline progress bar, talks to wafer_predict_server.py",
        PIPELINE_PROGRESS_HTML, PIPELINE_PROGRESS_CSS, PIPELINE_PROGRESS_JS, size_x=12, size_y=6,
    )

    old = widgets[target_id]
    widgets[target_id] = {
        **old,
        "typeFullFqn": pipeline_progress_fqn,
        "type": "latest",
        "config": {
            "datasources": [entity_datasource(entity_alias_id, [
                data_key("pipeline_stage", "timeseries", "pipeline_stage"),
                data_key("pipeline_stage_error_node", "timeseries", "pipeline_stage_error_node"),
            ])],
            "title": "파이프라인 실행", "showTitle": True, "settings": {},
        },
    }

    result = save_dashboard(token, dashboard)
    print("updated Wafer Detail dashboard id:", result["id"]["id"])
    print("pipeline_progress_fqn:", pipeline_progress_fqn)


if __name__ == "__main__":
    if "--apply-pipeline-progress" in sys.argv:
        apply_pipeline_progress_widget()
    else:
        main()

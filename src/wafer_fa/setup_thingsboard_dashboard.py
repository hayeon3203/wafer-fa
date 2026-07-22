"""One-time setup: create the wafer-fa custom widget types + the 3-tab dashboard
(Monitoring / Root Cause / Process) in ThingsBoard. Re-running creates duplicates
(no upsert) -- only meant to be run once against a fresh tenant.
"""
import json
import os
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
                        controller_script, default_config, size_x=8, size_y=5):
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
            "defaultConfig": json.dumps(default_config),
        },
    }
    resp = requests.post(f"{THINGSBOARD_URL}/api/widgetType", headers=headers, json=body)
    resp.raise_for_status()
    return resp.json()["fqn"]


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


def data_key(name, key_type="timeseries", label=None):
    return {"name": name, "type": key_type, "label": label or name, "settings": {}}


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


def main():
    token = login()

    lot_analysis_fqn = create_widget_type(
        token, "Wafer-FA Lot Analysis", "Lot select + per-pattern count table + trend bars",
        LOT_ANALYSIS_HTML, LOT_ANALYSIS_CSS, LOT_ANALYSIS_JS,
        {"datasources": [], "showTitle": True, "title": "Lot Analysis", "settings": {}},
        size_x=12, size_y=8,
    )
    slider_fqn = create_widget_type(
        token, "Wafer-FA Threshold Slider", "Writable model confidence threshold slider",
        SLIDER_HTML, SLIDER_CSS, SLIDER_JS,
        {"datasources": [], "showTitle": True, "title": "Model Threshold", "settings": {}},
        size_x=6, size_y=3,
    )

    alias_id = str(uuid.uuid4())
    entity_aliases = {
        alias_id: {
            "id": alias_id,
            "alias": "Wafer-FA Pipeline Device",
            "filter": {
                "type": "singleEntity",
                "singleEntity": {"entityType": "DEVICE", "id": DEVICE_ID},
                "resolveMultiple": False,
            },
        }
    }

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

    widgets = {}

    wid, w = widget(
        "cards.value_card", "latest", 6, 5, 0, 0,
        {
            "datasources": [entity_datasource(alias_id, [
                {**data_key("die_yield", "timeseries", "die_yield"),
                 "units": "%", "decimals": 1,
                 "usePostProcessing": True,
                 "postFuncBody": "return value * 100;"},
            ])],
            "title": "Die-level Yield (최근 웨이퍼)",
            "showTitle": True,
            "settings": {"labelPosition": "top", "layout": "square", "showLabel": True,
                         "showIcon": True, "icon": "check_circle", "showDate": True},
        },
    )
    widgets[wid] = w

    wid, w = widget(
        lot_analysis_fqn, "latest", 14, 8, 0, 6,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("lot_pattern_counts", "attribute", "lot_pattern_counts"),
            ])],
            "title": "Lot 선택 / 패턴별 웨이퍼 수 / Lot Trend",
            "showTitle": True,
            "settings": {},
        },
    )
    widgets[wid] = w

    wid, w = widget(
        slider_fqn, "latest", 6, 3, 5, 0,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("confidence_threshold", "attribute", "confidence_threshold"),
            ])],
            "title": "모델 임계값 슬라이더",
            "showTitle": True,
            "settings": {},
        },
    )
    widgets[wid] = w

    monitoring_layout = {wid_: {"sizeX": w_["sizeX"], "sizeY": w_["sizeY"], "row": w_["row"], "col": w_["col"]}
                          for wid_, w_ in widgets.items()}
    monitoring_widget_ids = list(widgets.keys())

    wid, w = widget(
        "cards.html_value_card", "latest", 10, 8, 0, 0,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("defect_class", "timeseries", "defect_class"),
                data_key("confidence", "timeseries", "confidence"),
                data_key("severity", "timeseries", "severity"),
                data_key("description", "timeseries", "description"),
                data_key("root_cause", "timeseries", "root_cause"),
                data_key("recipe", "timeseries", "recipe"),
            ])],
            "title": "원인분석 (최근 웨이퍼 릴레이 결과)",
            "showTitle": True,
            "settings": {
                "cardCss": (
                    ".rc { padding: 16px; font-family: Roboto, sans-serif; overflow-y: auto; height: 100%;"
                    " box-sizing: border-box; }\n"
                    ".rc h3 { margin: 12px 0 4px; font-size: 13px; color: #888; text-transform: uppercase; }\n"
                    ".rc p { margin: 0; font-size: 14px; line-height: 1.5; }"
                ),
                "cardHtml": (
                    "<div class='rc'>"
                    "<h3>예측 결함 / 신뢰도 / 심각도</h3>"
                    "<p><b>${defect_class}</b> (${confidence:2}) — <b>${severity}</b></p>"
                    "<h3>결함 설명</h3><p>${description}</p>"
                    "<h3>원인 분석</h3><p>${root_cause}</p>"
                    "<h3>해결책 제안</h3><p>${recipe}</p>"
                    "</div>"
                ),
            },
        },
    )
    widgets[wid] = w
    root_cause_widgets = {wid: {"sizeX": w["sizeX"], "sizeY": w["sizeY"], "row": w["row"], "col": w["col"]}}
    root_cause_widget_ids = [wid]

    wid, w = widget(
        "cards.html_value_card", "latest", 6, 8, 0, 10,
        {
            "datasources": [entity_datasource(alias_id, [
                data_key("wafer_image", "timeseries", "wafer_image"),
                data_key("lot_id", "timeseries", "lot_id"),
                data_key("wafer_index", "timeseries", "wafer_index"),
            ])],
            "title": "개별 웨이퍼맵",
            "showTitle": True,
            "settings": {
                "cardCss": (
                    ".wf { display:flex; flex-direction:column; align-items:center; justify-content:center;"
                    " height:100%; font-family: Roboto, sans-serif; }\n"
                    ".wf img { max-width: 90%; max-height: 70%; border: 1px solid #eee; }\n"
                    ".wf .cap { margin-top: 8px; font-size: 12px; color: #888; }"
                ),
                "cardHtml": (
                    "<div class='wf'><img src='data:image/png;base64,${wafer_image}' />"
                    "<div class='cap'>lot ${lot_id} / wafer #${wafer_index}</div></div>"
                ),
            },
        },
    )
    widgets[wid] = w
    root_cause_widgets[wid] = {"sizeX": w["sizeX"], "sizeY": w["sizeY"], "row": w["row"], "col": w["col"]}
    root_cause_widget_ids.append(wid)

    wid, w = widget(
        "cards.html_value_card", "latest", 16, 8, 8, 0,
        {
            "datasources": [entity_datasource(alias_id, composite_keys)],
            "title": "Composite 웨이퍼맵 히트맵 (패턴별 평균)",
            "showTitle": True,
            "settings": {
                "cardCss": (
                    ".grid { display:flex; flex-wrap:wrap; gap:12px; padding:12px; font-family: Roboto, sans-serif; }\n"
                    ".composite-item { width: 110px; text-align:center; }\n"
                    ".composite-item img { width: 96px; height: 96px; border-radius: 50%; }\n"
                    ".composite-label { font-size: 12px; color:#666; margin-top:4px; }"
                ),
                "cardHtml": f"<div class='grid'>{composite_imgs}</div>",
            },
        },
    )
    widgets[wid] = w
    root_cause_widgets[wid] = {"sizeX": w["sizeX"], "sizeY": w["sizeY"], "row": w["row"], "col": w["col"]}
    root_cause_widget_ids.append(wid)

    wid, w = widget(
        "cards.html_card", "static", 12, 6, 0, 0,
        {
            "datasources": [],
            "title": "장비 텔레메트리 상관관계 (Phase 3)",
            "showTitle": True,
            "settings": {
                "cardCss": (
                    ".ph { display:flex; align-items:center; justify-content:center; height:100%;"
                    " font-size:16px; color:#999; font-family: Roboto, sans-serif; text-align:center; padding:24px;"
                    " box-sizing:border-box; }"
                ),
                "cardHtml": (
                    "<div class='ph'>Phase 3 예정 — 합성 장비 로그(SECS/GEM) 연동 후 "
                    "결함-공정 상관관계 위젯이 이 탭에 채워집니다.<br/>"
                    "(TimescaleDB hypertable equipment_telemetry 는 이미 준비되어 있음)</div>"
                ),
            },
        },
    )
    widgets[wid] = w
    process_widgets = {wid: {"sizeX": w["sizeX"], "sizeY": w["sizeY"], "row": w["row"], "col": w["col"]}}

    dashboard = {
        "title": "Wafer-FA Demo Dashboard",
        "configuration": {
            "widgets": widgets,
            "states": {
                "default": {
                    "name": "Monitoring",
                    "root": True,
                    "layouts": {
                        "main": {
                            "widgets": {k: monitoring_layout[k] for k in monitoring_widget_ids},
                            "gridSettings": {"backgroundColor": "#fff", "columns": 24, "margin": 10},
                        }
                    },
                },
                "root_cause": {
                    "name": "Root Cause",
                    "root": False,
                    "layouts": {
                        "main": {
                            "widgets": root_cause_widgets,
                            "gridSettings": {"backgroundColor": "#fff", "columns": 24, "margin": 10},
                        }
                    },
                },
                "process": {
                    "name": "Process (Phase 3)",
                    "root": False,
                    "layouts": {
                        "main": {
                            "widgets": process_widgets,
                            "gridSettings": {"backgroundColor": "#fff", "columns": 24, "margin": 10},
                        }
                    },
                },
            },
            "entityAliases": entity_aliases,
            "settings": {},
        },
    }

    headers = {"X-Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(f"{THINGSBOARD_URL}/api/dashboard", headers=headers, json=dashboard)
    resp.raise_for_status()
    result = resp.json()
    print("dashboard id:", result["id"]["id"])
    print("lot_analysis_fqn:", lot_analysis_fqn)
    print("slider_fqn:", slider_fqn)


if __name__ == "__main__":
    main()


-- 1) widget_type descriptor: new infinite-scroll fetch-based gallery HTML/CSS/JS
update widget_type
set descriptor = '{"type": "latest", "sizeX": 10, "sizeY": 9, "resources": [], "templateHtml": "\n<div class=\"wg-scroll\">\n  <div class=\"wg-status\"></div>\n  <div class=\"wg-wrap\"></div>\n  <div class=\"wg-sentinel\"></div>\n</div>\n", "templateCss": "\n.wg-scroll { height: 100%; overflow-y: auto; box-sizing: border-box; font-family: Roboto, sans-serif; }\n.wg-status { padding: 6px 10px; font-size: 11px; color: #999; }\n.wg-wrap { display: flex; flex-wrap: wrap; gap: 10px; padding: 0 10px 10px; }\n.wg-item { width: 90px; text-align: center; }\n.wg-item img { width: 80px; height: 80px; border: 1px solid #eee; border-radius: 4px; }\n.wg-cap { font-size: 11px; color: #555; margin-top: 4px; }\n.wg-sub { color: #999; }\n.wg-sentinel { height: 1px; }\n", "controllerScript": "\nvar API_PORT = 8091;\nvar PAGE_SIZE = 40;\n\nself.onInit = function() {\n    self.ctx.wgOffset = 0;\n    self.ctx.wgTotal = null;\n    self.ctx.wgLoading = false;\n    var container = self.ctx.$container[0];\n    container.querySelector(''.wg-scroll'').addEventListener(''scroll'', onScroll);\n    loadMore();\n};\n\nfunction apiBase() {\n    return ''http://'' + window.location.hostname + '':'' + API_PORT;\n}\n\nfunction onScroll(e) {\n    var el = e.target;\n    if (el.scrollTop + el.clientHeight > el.scrollHeight - 200) {\n        loadMore();\n    }\n}\n\nfunction loadMore() {\n    if (self.ctx.wgLoading) return;\n    if (self.ctx.wgTotal !== null && self.ctx.wgOffset >= self.ctx.wgTotal) return;\n    self.ctx.wgLoading = true;\n    var container = self.ctx.$container[0];\n    var statusEl = container.querySelector(''.wg-status'');\n    var wrapEl = container.querySelector(''.wg-wrap'');\n    statusEl.textContent = ''로딩 중...'';\n\n    var url = apiBase() + ''/api/wafers?offset='' + self.ctx.wgOffset + ''&limit='' + PAGE_SIZE;\n    fetch(url).then(function(r) { return r.json(); }).then(function(data) {\n        self.ctx.wgTotal = data.total;\n        self.ctx.wgOffset += data.items.length;\n        data.items.forEach(function(s) {\n            var item = document.createElement(''div'');\n            item.className = ''wg-item'';\n            item.innerHTML = ''<img src=\"data:image/png;base64,'' + s.image + ''\" />'' +\n                ''<div class=\"wg-cap\">'' + s.label + ''<br/><span class=\"wg-sub\">'' + s.lot_id + '' #'' + s.wafer_index + ''</span></div>'';\n            wrapEl.appendChild(item);\n        });\n        statusEl.textContent = self.ctx.wgOffset + '' / '' + data.total + '' 웨이퍼 로드됨'';\n        self.ctx.wgLoading = false;\n        if (data.items.length === 0) return;\n    }).catch(function(err) {\n        statusEl.textContent = ''wafer_browser_server(:'' + API_PORT + '') 연결 실패 — 서버 가동 여부 확인 필요'';\n        self.ctx.wgLoading = false;\n    });\n}\n\nself.onDataUpdated = function() {};\nself.onResize = function() {};\nself.onDestroy = function() {};\n", "settingsSchema": "{}", "dataKeySettingsSchema": "{}", "defaultConfig": "{\"datasources\": [], \"showTitle\": true, \"title\": \"Wafer-FA Wafer Gallery\", \"settings\": {}}"}'
where fqn = 'wafer_fa_wafer_gallery';

-- 2) swap positions of Composite heatmap <-> Wafer gallery on 'Wafer Overview'
--    (the states.default.layouts.main.widgets map is what TB actually renders from)
update dashboard
set configuration = jsonb_set(
  jsonb_set(
    configuration::jsonb,
    '{states,default,layouts,main,widgets,0b7e30f8-ce6d-4c52-a7cd-3c39d571d706}',
    '{"col": 0, "row": 5, "sizeX": 17, "sizeY": 12}'
  ),
  '{states,default,layouts,main,widgets,f5cef9c2-5df4-4f19-8a9c-e0670966a684}',
  '{"col": 17, "row": 5, "sizeX": 9, "sizeY": 12}'
)::varchar
where title = 'Wafer Overview';

-- 3) rename gallery widget + drop its now-unused TB datasource (it fetches from
--    wafer_browser_server.py directly instead)
update dashboard
set configuration = jsonb_set(
  jsonb_set(
    configuration::jsonb,
    '{widgets,f5cef9c2-5df4-4f19-8a9c-e0670966a684,config,title}',
    '"전체 웨이퍼 데이터"'
  ),
  '{widgets,f5cef9c2-5df4-4f19-8a9c-e0670966a684,config,datasources}',
  '[]'
)::varchar
where title = 'Wafer Overview';

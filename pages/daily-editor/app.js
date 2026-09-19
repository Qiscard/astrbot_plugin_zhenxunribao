/* 真寻日报编辑器：画布点击编辑（同 bot_menu）+ 每模块「配置接口」+ 真实预览 */
(function () {
  "use strict";

  // 模块类型元数据（label/hasCount/hasItems 为前端渲染所需的稳定字段）
  var MODULE_TYPES = {
    anime: { label: "今日新番", hasCount: true, def: 4 },
    news: { label: "60s读懂世界", hasCount: true, def: 10 },
    english: { label: "每日英语", hasCount: true, def: 1 },
    essay: { label: "每日一文", hasCount: true, def: 1 },
    aidaily: { label: "AI早报", hasCount: true, def: 10 },
    rmrbpdf: { label: "每日人民日报", hasCount: false },
    cartoon: { label: "今日追番", hasCount: true, def: 6 },
    shici: { label: "每日诗词", hasCount: true, def: 1 },
    yulu: { label: "语录", hasCount: true, def: 1 },
    countdown: { label: "自定义倒计时", hasItems: true },
  };
  var QUOTE_SOURCES = {
    hitokoto: "今日一言", duji: "毒鸡汤", mingyan: "名人名言",
    tiangou: "舔狗日记", gaoxiao: "搞笑语录", xiehouyu: "歇后语",
  };
  // 各模块可配置的接口请求参数（后端 meta 会覆盖；此处为离线兜底）
  var PARAM_SCHEMA = {
    aidaily: [
      { key: "type", label: "返回格式", type: "select", options: [
        { value: "txt", label: "纯文本" }, { value: "md", label: "Markdown" }, { value: "image", label: "渲染图" },
      ], default: "txt" },
      { key: "date", label: "日期", type: "text", placeholder: "YYYY-MM-DD，留空当天", default: "" },
    ],
    rmrbpdf: [
      { key: "date", label: "日期", type: "text", placeholder: "YYYY-MM-DD，留空当天", default: "" },
    ],
    cartoon: [
      { key: "date", label: "日期", type: "text", placeholder: "YYYYMMDD，留空当天", default: "" },
    ],
    shici: [
      { key: "keyword", label: "诗词关键词", type: "text", placeholder: "如：静夜思", default: "静夜思" },
    ],
    yulu: [
      { key: "type", label: "语录类型", type: "select", options: [
        { value: "", label: "随机" }, { value: "经典", label: "经典" }, { value: "动漫", label: "动漫" },
        { value: "恋爱", label: "恋爱" }, { value: "鼓励", label: "鼓励" }, { value: "孤独", label: "孤独" },
        { value: "搞笑", label: "搞笑" }, { value: "友情", label: "友情" }, { value: "歌词", label: "歌词" },
      ], default: "" },
    ],
  };
  var PH = {
    hist: "{{历史事件}}", anime: "{{新番标题}}", news: "{{新闻摘要}}",
    word: "{{word}}", mean: "{{中文释义}}", eg: "{{例句}}",
    cd: "{{倒计时}}", quote: "{{短句占位}}", from: "{{来源}}",
    riddle: "{{谜面}}",
  };
  var state = {
    moyu_title: "摸鱼日历", moyu_items: [], history_enabled: true,
    history_title: "历史上的今天", history_count: 4,
    top_source: "history",
    mid1_source: "anime", mid1_title: "今日新番", mid1_count: 4, mid1_params: {},
    mid2_source: "news", mid2_title: "60s读懂世界", mid2_count: 10, mid2_params: {},
    exchange_from: "USD", exchange_to: "CNY", exchange_amount: 100,
    quote_enabled: true, quote_title: "", quote_sources: ["hitokoto"], modules: [],
  };
  // 顶部/中部1/中部2 候选来源（后端 meta 会覆盖；此处为离线兜底）
  var TOP_SOURCES = { history: "历史上的今天", english: "每日英语", exchange: "实时汇率" };
  var MID1_SOURCES = { anime: "今日新番", cartoon: "今日追番", hbox: "小黑盒游戏" };
  var MID2_SOURCES = { news: "60s读懂世界", aidaily: "AI早报", rmrbpdf: "每日人民日报" };
  var bridge = null;

  function unwrap(r) {
    if (r && typeof r === "object" && "status" in r) {
      if (r.status === "error") throw new Error(r.message || "请求失败");
      if (r.status === "ok") return r.data || {};
    }
    return r || {};
  }
  function findBridge() {
    var cs = [
      window.AstrBotPluginPage, window.AstrBotPage, window.PluginPage,
      window.astrbot && window.astrbot.pluginPage,
    ];
    try {
      if (window.parent && window.parent !== window) {
        cs.push(window.parent.AstrBotPluginPage, window.parent.AstrBotPage, window.parent.PluginPage);
      }
    } catch (e) {}
    return cs.find(function (c) { return c && typeof c === "object"; }) || null;
  }
  async function resolveBridge() {
    var t0 = Date.now(), raw = findBridge();
    while (!raw) {
      if (Date.now() - t0 > 6000) throw new Error("未检测到 AstrBot 页面桥接");
      await new Promise(function (r) { setTimeout(r, 40); });
      raw = findBridge();
    }
    if (typeof raw.ready === "function") await raw.ready();
    var g = raw.apiGet || raw.get || raw.GET;
    var p = raw.apiPost || raw.post || raw.POST;
    if (typeof g !== "function" || typeof p !== "function") throw new Error("桥接缺少 apiGet/apiPost");
    return {
      apiGet: async function (path) { return unwrap(await g.call(raw, path)); },
      apiPost: async function (path, body) { return unwrap(await p.call(raw, path, body || {})); },
    };
  }
  function el(tag, a, kids) {
    var n = document.createElement(tag);
    if (a) {
      Object.keys(a).forEach(function (k) {
        if (k === "class") n.className = a[k];
        else if (k === "text") n.textContent = a[k];
        else if (k.indexOf("on") === 0) n.addEventListener(k.slice(2), a[k]);
        else n.setAttribute(k, a[k]);
      });
    }
    (kids || []).forEach(function (c) {
      if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }
  function move(arr, i, d) {
    var j = i + d;
    if (j < 0 || j >= arr.length) return;
    var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
  }
  // 判断 YYYY-MM-DD（一次性日期）是否已过期，用于画布区分正/倒计时
  function isPastDate(dateStr) {
    if (typeof dateStr !== "string") return false;
    var s = dateStr.trim();
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return false;
    var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    if (isNaN(d.getTime())) return false;
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    return d.getTime() < today.getTime();
  }
  function msg(t, e) {
    var b = document.getElementById("message");
    b.textContent = t;
    b.className = "message " + (e ? "error" : "success");
    clearTimeout(msg._t);
    msg._t = setTimeout(function () { b.className = "message hidden"; }, 3500);
  }
  function snapshot() { return JSON.parse(JSON.stringify(state)); }

  // ===== 画布渲染 =====
  function actionBtn(text, fn, danger) {
    return el("button", {
      class: "btn btn-mini" + (danger ? " btn-danger" : ""),
      type: "button", text: text, title: text,
      onclick: function (e) { e.preventDefault(); e.stopPropagation(); fn(); },
    });
  }
  function panel(tag, bodyNodes, opts) {
    opts = opts || {};
    var node = el("div", { class: "dp-panel" + (opts.selected ? " selected" : "") });
    node.appendChild(el("div", { class: "dp-tag", text: tag }));
    if (opts.actions && opts.actions.length) {
      var act = el("div", { class: "dp-panel-actions" });
      opts.actions.forEach(function (a) { act.appendChild(a); });
      node.appendChild(act);
    }
    (bodyNodes || []).forEach(function (b) { node.appendChild(b); });
    if (opts.onclick) node.addEventListener("click", opts.onclick);
    return node;
  }
  function rep(n, fn) { var a = []; for (var i = 0; i < n; i++) a.push(fn(i)); return a; }
  function apiBadge(mod) {
    var schema = PARAM_SCHEMA[mod.type];
    if (!schema || !schema.length) return null;
    var p = mod.params || {};
    var parts = schema.map(function (f) { return f.label + "：" + (p[f.key] || f.default || "默认"); });
    return el("div", { class: "dp-api-hint", text: "接口参数 · " + parts.join(" ｜ ") });
  }

  function renderCanvas() {
    var s = snapshot();
    var root = document.getElementById("preview");
    root.textContent = "";

    var header = el("div", { class: "dp-header" }, [
      el("div", { class: "dp-figure" }, [el("div", { class: "ph", text: "真寻" })]),
      el("div", { class: "dp-titles" }, [
        el("p", { class: "dp-title-cn", text: "真寻日报" }),
        el("p", { class: "dp-title-en", text: "MAHIRO NEWS" }),
      ]),
      el("div", { class: "dp-date" }, [
        el("div", { class: "w", text: "X" }),
        el("div", { class: "d", text: "YYYY年MM月DD日" }),
        el("div", { class: "l", text: "农历占位" }),
      ]),
    ]);

    var lead = el("div", { class: "dp-lead" + (s.top_source === "history" && s.history_enabled ? "" : " solo") });

    var moyuItems = (s.moyu_items.length ? s.moyu_items : [{ type: "holiday" }]).map(function (it) {
      var name = it.name || (it.type === "weekly" ? "周休日" : it.type === "custom" ? "自定义" : "{{节日}}");
      var dir = it.type === "custom" && isPastDate(it.date) ? "过了 " : "还剩 ";
      return el("div", { class: "dp-line" }, [
        el("span", { text: "距离 " }), el("b", { text: name }),
        el("span", { text: " " + dir }), el("b", { text: "N" }), el("span", { text: " 天" }),
      ]);
    });
    lead.appendChild(panel(s.moyu_title || "摸鱼日历", [el("div", { class: "dp-list" }, moyuItems)], {
      onclick: function (e) { e.stopPropagation(); openModal({ kind: "moyu" }); },
    }));

    // 顶部模块：与摸鱼日历同行，单选 history/english/exchange
    if (s.top_source === "history" && s.history_enabled) {
      var hn = Math.max(1, s.history_count || 4);
      lead.appendChild(panel(s.history_title || "历史上的今天", [
        el("div", { class: "dp-list" }, rep(hn, function () {
          return el("div", { class: "dp-hist-item" }, [
            el("span", { class: "y", text: "YYYY年" }), el("span", { text: PH.hist }),
          ]);
        })),
      ], {
        onclick: function (e) { e.stopPropagation(); openModal({ kind: "top" }); },
      }));
    } else if (s.top_source === "english") {
      lead.appendChild(panel("每日英语", [
        el("div", {}, [
          el("div", {}, [el("span", { class: "dp-en-word", text: PH.word }), el("span", { class: "dp-en-ph", text: "/phonetic/" })]),
          el("div", { class: "muted", text: "n. " + PH.mean }), el("div", { class: "muted", text: PH.eg }),
        ]),
      ], {
        onclick: function (e) { e.stopPropagation(); openModal({ kind: "top" }); },
      }));
    } else if (s.top_source === "exchange") {
      lead.appendChild(panel("实时汇率", [
        el("div", { class: "dp-exchange" }, [
          el("span", { class: "dp-ex-amt", text: s.exchange_amount + " " + s.exchange_from }),
          el("span", { text: " ≈ " }),
          el("b", { text: "XXX.XX " + s.exchange_to }),
        ]),
        el("div", { class: "muted", text: "参考汇率 1 " + s.exchange_from + " = X.XXXX " + s.exchange_to }),
      ], {
        onclick: function (e) { e.stopPropagation(); openModal({ kind: "top" }); },
      }));
    }

    var body = el("div", { class: "dp-body" });

    // ---- 中部模块1：番剧/游戏类（固定面板，单选） ----
    var mid1Body = null;
    if (s.mid1_source === "anime") {
      mid1Body = el("div", { class: "dp-anime" }, rep(Math.max(1, s.mid1_count || 4), function () {
        return el("div", { class: "card" }, [el("div", { class: "cover", text: "封面" }), el("p", { text: PH.anime })]);
      }));
    } else if (s.mid1_source === "cartoon") {
      mid1Body = el("ul", { class: "dp-news" }, rep(Math.max(1, s.mid1_count || 6), function (i) {
        return el("li", { text: "{{番剧标题}} " + (i + 1) + "  {{更新时间}}" });
      }));
    } else if (s.mid1_source === "hbox") {
      mid1Body = el("div", { class: "dp-anime" }, rep(Math.max(1, s.mid1_count || 4), function () {
        return el("div", { class: "card" }, [el("div", { class: "cover", text: "游戏封面" }), el("p", { text: "{{游戏名}}" })]);
      }));
    }
    if (mid1Body) {
      body.appendChild(panel(s.mid1_title || MID1_SOURCES[s.mid1_source], [mid1Body], {
        onclick: function (e) { e.stopPropagation(); openModal({ kind: "mid1" }); },
      }));
    }

    // ---- 中部模块2：新闻/资讯类（固定面板，单选） ----
    var mid2Body = null;
    if (s.mid2_source === "news") {
      mid2Body = el("ul", { class: "dp-news" }, rep(Math.max(1, s.mid2_count || 6), function (i) {
        return el("li", { text: PH.news + " " + (i + 1) });
      }));
    } else if (s.mid2_source === "aidaily") {
      mid2Body = el("ul", { class: "dp-news" }, rep(Math.max(1, s.mid2_count || 6), function (i) {
        return el("li", { text: "{{AI早报条目}} " + (i + 1) });
      }));
    } else if (s.mid2_source === "rmrbpdf") {
      mid2Body = el("div", { class: "dp-essay" }, [
        el("div", { class: "dp-essay-title", text: "{{日期}} 人民日报" }),
        el("div", { class: "muted", text: "今日电子版 PDF" }),
        el("div", { class: "muted", text: "{{pdf_url}}" }),
      ]);
    }
    if (mid2Body) {
      body.appendChild(panel(s.mid2_title || MID2_SOURCES[s.mid2_source], [mid2Body], {
        onclick: function (e) { e.stopPropagation(); openModal({ kind: "mid2" }); },
      }));
    }

    (s.modules || []).forEach(function (mod, idx) {
      if (mod.enabled === false) return;
      var content = [];
      if (mod.type === "anime") {
        content.push(el("div", { class: "dp-anime" }, rep(Math.max(1, mod.count || 4), function () {
          return el("div", { class: "card" }, [el("div", { class: "cover", text: "封面" }), el("p", { text: PH.anime })]);
        })));
      } else if (mod.type === "news") {
        content.push(el("ul", { class: "dp-news" }, rep(Math.max(1, mod.count || 6), function (i) {
          return el("li", { text: PH.news + " " + (i + 1) });
        })));
      } else if (mod.type === "english") {
        content.push(el("div", {}, [
          el("div", {}, [el("span", { class: "dp-en-word", text: PH.word }), el("span", { class: "dp-en-ph", text: "/phonetic/" })]),
          el("div", { class: "muted", text: "n. " + PH.mean }), el("div", { class: "muted", text: PH.eg }),
        ]));
      } else if (mod.type === "essay") {
        content.push(el("div", { class: "dp-essay" }, [
          el("div", { class: "dp-essay-title", text: "{{文章标题}}" }),
          el("div", { class: "muted", text: "{{文章正文占位，每日一文随机美文}}" }),
          el("div", { class: "dp-essay-author", text: "—— {{作者}}" }),
        ]));
      } else if (mod.type === "aidaily") {
        content.push(el("ul", { class: "dp-news" }, rep(Math.max(1, mod.count || 6), function (i) {
          return el("li", { text: "{{AI早报条目}} " + (i + 1) });
        })));
      } else if (mod.type === "rmrbpdf") {
        content.push(el("div", { class: "dp-essay" }, [
          el("div", { class: "dp-essay-title", text: "{{日期}} 人民日报" }),
          el("div", { class: "muted", text: "今日电子版 PDF" }),
          el("div", { class: "muted", text: "{{pdf_url}}" }),
        ]));
      } else if (mod.type === "cartoon") {
        content.push(el("ul", { class: "dp-news" }, rep(Math.max(1, mod.count || 6), function (i) {
          return el("li", { text: "{{番剧标题}} " + (i + 1) + "  {{更新时间}}" });
        })));
      } else if (mod.type === "shici") {
        content.push(el("div", { class: "dp-essay" }, [
          el("div", { class: "dp-essay-title", text: "{{诗词标题}}" }),
          el("div", { class: "muted", text: "{{作者}}·{{朝代}}" }),
          el("div", { class: "muted", text: "{{诗词正文}}" }),
        ]));
      } else if (mod.type === "yulu") {
        content.push(el("div", { class: "dp-essay" }, [
          el("div", { class: "dp-essay-title", text: "{{语录文本}}" }),
          el("div", { class: "dp-essay-author", text: "—— {{作者}}" }),
        ]));
      } else if (mod.type === "countdown") {
        var items = (mod.items && mod.items.length) ? mod.items : [{ name: PH.cd }];
        content.push(el("div", { class: "dp-list" }, items.map(function (it) {
          return el("div", { class: "dp-line" }, [
            el("span", { text: "距离 " }), el("b", { text: it.name || PH.cd }),
            el("span", { text: " 还剩 " }), el("b", { text: "N" }), el("span", { text: " 天" }),
          ]);
        })));
      }
      var badge = apiBadge(mod);
      if (badge) content.push(badge);
      body.appendChild(panel(mod.title || (MODULE_TYPES[mod.type] && MODULE_TYPES[mod.type].label) || mod.type, content, {
        onclick: function (e) { e.stopPropagation(); openModal({ kind: "module", index: idx }); },
        actions: [
          actionBtn("↑", function () { move(state.modules, idx, -1); saveSilent(); renderCanvas(); }),
          actionBtn("↓", function () { move(state.modules, idx, 1); saveSilent(); renderCanvas(); }),
          actionBtn("隐藏", function () { state.modules[idx].enabled = false; saveSilent(); renderCanvas(); }),
          actionBtn("删除", function () { state.modules.splice(idx, 1); saveSilent(); renderCanvas(); }, true),
        ],
      }));
    });

    var hiddenMods = (s.modules || []).filter(function (m) { return m.enabled === false; });
    if (hiddenMods.length) {
      body.appendChild(el("div", { class: "dp-hidden-bar" }, [el("span", { class: "hint", text: "已隐藏模块：" })].concat(
        hiddenMods.map(function (m) {
          var hidx = s.modules.indexOf(m);
          return el("button", {
            class: "dp-hidden-chip", type: "button",
            text: "＋ " + (m.title || (MODULE_TYPES[m.type] && MODULE_TYPES[m.type].label) || m.type),
            onclick: function (e) {
              e.stopPropagation();
              if (hidx >= 0) state.modules[hidx].enabled = true;
              saveSilent(); renderCanvas();
            },
          });
        }),
      )));
    }
    body.appendChild(el("div", {
      class: "dp-add", text: "＋ 添加中间模块",
      onclick: function (e) { e.stopPropagation(); addModule(); },
    }));

    var mainKids = [header, lead];
    if (s.top_source === "history" && !s.history_enabled) {
      mainKids.push(el("div", { class: "dp-hidden-bar first" }, [
        el("span", { class: "hint", text: "已隐藏：" }),
        el("button", {
          class: "dp-hidden-chip", type: "button", text: "＋ " + (s.history_title || "历史上的今天"),
          onclick: function (e) { e.stopPropagation(); state.history_enabled = true; saveSilent(); renderCanvas(); },
        }),
      ]));
    }
    mainKids.push(body);

    // 底部模块：短句/谜语来源单选
    var qKey = s.quote_sources[0] || "hitokoto";
    var qTitle = s.quote_title || QUOTE_SOURCES[qKey] || "今日一言";
    if (s.quote_enabled) {
      var qBody = qKey === "riddle"
        ? [el("div", { class: "dp-riddle" }, [el("div", { class: "dp-riddle-mimian", text: PH.riddle })])]
        : [el("div", { class: "dp-quote" }, [el("div", {}, [
            el("div", { class: "qt", text: '" ' + PH.quote + ' "' }),
            el("span", { class: "qf", text: "—— " + PH.from }),
          ])])];
      mainKids.push(panel(qTitle, qBody, {
        onclick: function (e) { e.stopPropagation(); openModal({ kind: "quote" }); },
        actions: [actionBtn("隐藏", function () { state.quote_enabled = false; saveSilent(); renderCanvas(); })],
      }));
    } else {
      mainKids.push(el("div", { class: "dp-hidden-bar first" }, [
        el("span", { class: "hint", text: "已隐藏：" }),
        el("button", {
          class: "dp-hidden-chip", type: "button", text: "＋ " + qTitle,
          onclick: function (e) { e.stopPropagation(); state.quote_enabled = true; saveSilent(); renderCanvas(); },
        }),
      ]));
    }
    mainKids.push(el("div", { class: "dp-foot", text: "ZHENXUN DAILY EDETOR · 布局占位画布" }));
    root.appendChild(el("div", { class: "dp-main" }, mainKids));
  }

  // ===== 模态框（点击画布元素打开） =====
  function openModal(target) {
    var title = document.getElementById("modal-title");
    var body = document.getElementById("modal-body");
    body.textContent = "";
    if (target.kind === "moyu") { title.textContent = "编辑：摸鱼日历"; renderMoyuModal(body); }
    else if (target.kind === "top") { title.textContent = "编辑：顶部模块"; renderTopModal(body); }
    else if (target.kind === "mid1") { title.textContent = "编辑：中部模块1"; renderMidModal(body, 1); }
    else if (target.kind === "mid2") { title.textContent = "编辑：中部模块2"; renderMidModal(body, 2); }
    else if (target.kind === "quote") { title.textContent = "编辑：底部模块"; renderQuoteModal(body); }
    else if (target.kind === "module") { title.textContent = "编辑中间模块"; renderModuleModal(body, target.index); }
    document.getElementById("modal").classList.remove("hidden");
  }
  function closeModal() { document.getElementById("modal").classList.add("hidden"); }
  function fieldRow(label, input) {
    return el("div", { class: "f-row" }, [el("span", { text: label }), input]);
  }

  function renderMoyuModal(body) {
    body.textContent = "";
    var title = el("input", { value: state.moyu_title || "摸鱼日历" });
    title.addEventListener("input", function () { state.moyu_title = title.value; renderCanvas(); });
    body.appendChild(fieldRow("标题", title));

    body.appendChild(el("div", { class: "f-label", text: "计时项（最多10条）" }));
    var list = el("div", { class: "f-list" });
    state.moyu_items.forEach(function (it, idx) {
      var type = it.type || (it.date ? "custom" : "holiday");
      var sel = el("select", { class: "grow" });
      [["holiday", "节假日"], ["custom", "自定义"], ["weekly", "周期"]].forEach(function (pair) {
        var o = el("option", { value: pair[0], text: pair[1] });
        if (type === pair[0]) o.selected = true;
        sel.appendChild(o);
      });
      var name = el("input", { class: "grow", value: it.name || "", placeholder: "前段文本（如：元旦）" });
      var date = el("input", { class: "grow", value: it.date || "", placeholder: "YYYY-MM-DD 或 MM-DD" });
      sel.addEventListener("change", function () {
        var nt = sel.value, n = { type: nt };
        if (nt === "custom") { n.name = name.value || "自定义"; n.date = date.value || ""; }
        if (nt === "weekly") { n.name = name.value || "周休日"; n.weekday = 6; }
        state.moyu_items[idx] = n; renderCanvas(); renderMoyuModal(body);
      });
      name.addEventListener("input", function () { it.name = name.value; renderCanvas(); });
      date.addEventListener("input", function () { if (type === "custom") { it.date = date.value; renderCanvas(); } });
      var row = el("div", { class: "f-item" }, [sel]);
      if (type !== "holiday") row.appendChild(name);
      if (type === "custom") row.appendChild(date);
      row.appendChild(el("button", {
        class: "btn btn-mini", type: "button", text: "✕",
        onclick: function () { state.moyu_items.splice(idx, 1); renderCanvas(); renderMoyuModal(body); },
      }));
      list.appendChild(row);
    });
    body.appendChild(list);
    body.appendChild(el("div", { class: "f-row" }, [
      el("button", {
        class: "btn", type: "button", text: "＋ 添加计时项",
        onclick: function () {
          if (state.moyu_items.length >= 10) return msg("最多10条", true);
          state.moyu_items.push({ type: "holiday" });
          renderCanvas(); renderMoyuModal(body);
        },
      }),
    ]));
  }

  // 通用单选来源面板：从 candidates 里选一个，切换时更新 state 并刷新画布
  function sourceSelect(candidates, cur, onChange) {
    var sel = el("select", { class: "grow" });
    Object.keys(candidates).forEach(function (k) {
      var o = el("option", { value: k, text: candidates[k] });
      if (cur === k) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () { onChange(sel.value); renderCanvas(); });
    return sel;
  }

  function renderTopModal(body) {
    body.textContent = "";
    body.appendChild(el("div", { class: "f-label", text: "顶部模块来源（单选）" }));
    body.appendChild(fieldRow("来源", sourceSelect(TOP_SOURCES, state.top_source, function (v) {
      state.top_source = v;
      if (v === "history") state.history_enabled = true;
      renderTopModal(body);
    })));
    if (state.top_source === "history") {
      var title = el("input", { value: state.history_title || "历史上的今天" });
      title.addEventListener("input", function () { state.history_title = title.value; renderCanvas(); });
      body.appendChild(fieldRow("标题", title));
      var count = el("input", { type: "number", min: "1", max: "20", value: String(state.history_count || 4) });
      count.addEventListener("input", function () { state.history_count = Math.max(1, Number(count.value) || 4); renderCanvas(); });
      body.appendChild(fieldRow("条数", count));
      body.appendChild(el("div", { class: "f-row" }, [
        el("button", {
          class: "btn btn-danger", type: "button", text: "隐藏此面板",
          onclick: function () { state.history_enabled = false; saveSilent(); closeModal(); renderCanvas(); },
        }),
      ]));
    } else if (state.top_source === "exchange") {
      var from = el("input", { value: state.exchange_from || "USD" });
      from.addEventListener("input", function () { state.exchange_from = from.value.trim().toUpperCase(); renderCanvas(); });
      body.appendChild(fieldRow("源货币", from));
      var to = el("input", { value: state.exchange_to || "CNY" });
      to.addEventListener("input", function () { state.exchange_to = to.value.trim().toUpperCase(); renderCanvas(); });
      body.appendChild(fieldRow("目标货币", to));
      var amt = el("input", { type: "number", min: "0.01", value: String(state.exchange_amount || 100) });
      amt.addEventListener("input", function () { state.exchange_amount = Number(amt.value) || 100; renderCanvas(); });
      body.appendChild(fieldRow("换算金额", amt));
    }
  }

  function defaultParams(type) {
    var params = {};
    (PARAM_SCHEMA[type] || []).forEach(function (field) {
      params[field.key] = field.default || "";
    });
    return params;
  }

  function renderMidModal(body, slot) {
    body.textContent = "";
    var isMid1 = slot === 1;
    var srcKey = isMid1 ? "mid1_source" : "mid2_source";
    var titleKey = isMid1 ? "mid1_title" : "mid2_title";
    var countKey = isMid1 ? "mid1_count" : "mid2_count";
    var candidates = isMid1 ? MID1_SOURCES : MID2_SOURCES;
    body.appendChild(el("div", { class: "f-label", text: "中部模块" + slot + " 来源（单选）" }));
    body.appendChild(fieldRow("来源", sourceSelect(candidates, state[srcKey], function (v) {
      state[srcKey] = v;
      state[isMid1 ? "mid1_params" : "mid2_params"] = defaultParams(v);
      state[titleKey] = candidates[v];
      renderMidModal(body, slot);
    })));
    var title = el("input", { value: state[titleKey] || candidates[state[srcKey]] || "" });
    title.addEventListener("input", function () { state[titleKey] = title.value; renderCanvas(); });
    body.appendChild(fieldRow("标题", title));
    var count = el("input", { type: "number", min: "1", max: "30", value: String(state[countKey] || 4) });
    count.addEventListener("input", function () { state[countKey] = Math.max(1, Number(count.value) || 4); renderCanvas(); });
    body.appendChild(fieldRow("条数", count));
    var slotModule = moduleForSlot(isMid1 ? "mid1" : "mid2");
    renderApiConfigSection(body, slotModule, "配置接口");
    // 参数输入绑定到槽位状态，而不是临时模块副本。
    if (PARAM_SCHEMA[slotModule.type]) {
      var paramSection = body.lastElementChild;
      Array.prototype.forEach.call(paramSection.querySelectorAll("input, select"), function (input, i) {
        var field = PARAM_SCHEMA[slotModule.type][i];
        if (!field) return;
        input.addEventListener("input", function () {
          slotModule.params[field.key] = input.value;
          applySlotModule(isMid1 ? "mid1" : "mid2", slotModule);
          renderCanvas();
        });
        input.addEventListener("change", function () {
          slotModule.params[field.key] = input.value;
          applySlotModule(isMid1 ? "mid1" : "mid2", slotModule);
          renderCanvas();
        });
      });
    }
  }

  function renderHistoryModal(body) {
    // 保留旧入口（向后兼容 history 弹窗），内部代理到 renderTopModal
    renderTopModal(body);
  }

  function renderQuoteModal(body) {
    body.textContent = "";
    body.appendChild(el("div", { class: "f-label", text: "底部模块来源（可多选，每次随机取其一）" }));
    var list = el("div", { class: "dp-list" });
    Object.keys(QUOTE_SOURCES).forEach(function (key) {
      var cb = el("input", { type: "checkbox" });
      cb.checked = state.quote_sources.indexOf(key) !== -1;
      cb.addEventListener("change", function () {
        var i = state.quote_sources.indexOf(key);
        if (cb.checked && i === -1) state.quote_sources.push(key);
        if (!cb.checked && i !== -1) state.quote_sources.splice(i, 1);
        if (!state.quote_sources.length) {
          state.quote_sources.push(key);
          cb.checked = true;
        }
        renderCanvas();
      });
      list.appendChild(el("label", { class: "f-item" }, [cb, document.createTextNode(QUOTE_SOURCES[key])]));
    });
    body.appendChild(list);
    var title = el("input", { value: state.quote_title || "", placeholder: "留空按来源显示" });
    title.addEventListener("input", function () { state.quote_title = title.value; renderCanvas(); });
    body.appendChild(fieldRow("标题", title));
    body.appendChild(el("div", { class: "f-section-hint", text: "互动谜语类仅展示谜面；答题/灯谜保留为聊天命令，不进日报。" }));
    body.appendChild(el("div", { class: "f-row" }, [
      el("button", {
        class: "btn btn-danger", type: "button", text: "隐藏此面板",
        onclick: function () { state.quote_enabled = false; saveSilent(); closeModal(); renderCanvas(); },
      }),
    ]));
  }

  function renderApiConfigSection(body, mod, title) {
    var schema = PARAM_SCHEMA[mod.type];
    if (!schema || !schema.length) return;
    var sec = el("div", { class: "f-section" }, [
      el("div", { class: "f-section-title", text: title || "配置接口" }),
      el("div", { class: "f-section-hint", text: "该模块的接口请求参数（key/token 在插件配置界面统一设置）" }),
    ]);
    if (!mod.params) mod.params = {};
    schema.forEach(function (f) {
      var cur = mod.params[f.key];
      if (cur == null || cur === "") cur = f.default || "";
      var input;
      if (f.type === "select") {
        input = el("select");
        (f.options || []).forEach(function (opt) {
          var o = el("option", { value: opt.value, text: opt.label });
          if (String(cur) === String(opt.value)) o.selected = true;
          input.appendChild(o);
        });
        input.addEventListener("change", function () { mod.params[f.key] = input.value; renderCanvas(); });
      } else {
        input = el("input", { type: "text", value: cur, placeholder: f.placeholder || "" });
        input.addEventListener("input", function () { mod.params[f.key] = input.value; renderCanvas(); });
      }
      sec.appendChild(fieldRow(f.label, input));
    });
    body.appendChild(sec);
  }

  function moduleForSlot(slot) {
    if (slot === "mid1") return {
      type: state.mid1_source,
      title: state.mid1_title,
      count: state.mid1_count,
      params: state.mid1_params || {},
    };
    return {
      type: state.mid2_source,
      title: state.mid2_title,
      count: state.mid2_count,
      params: state.mid2_params || {},
    };
  }

  function applySlotModule(slot, mod) {
    if (slot === "mid1") {
      state.mid1_source = mod.type;
      state.mid1_title = mod.title;
      state.mid1_count = mod.count;
      state.mid1_params = mod.params || {};
    } else {
      state.mid2_source = mod.type;
      state.mid2_title = mod.title;
      state.mid2_count = mod.count;
      state.mid2_params = mod.params || {};
    }
  }

  function renderApiConfigSectionLegacy(body, mod) {
    renderApiConfigSection(body, mod, "配置接口");
  }

  function renderModuleModal(body, idx) {
    body.textContent = "";
    var mod = state.modules[idx];
    if (!mod) { closeModal(); return; }
    var meta = MODULE_TYPES[mod.type] || { label: mod.type };
    var typeSel = el("select");
    Object.keys(MODULE_TYPES).forEach(function (t) {
      var o = el("option", { value: t, text: MODULE_TYPES[t].label });
      if (mod.type === t) o.selected = true;
      typeSel.appendChild(o);
    });
    typeSel.addEventListener("change", function () {
      var t = typeSel.value, m = MODULE_TYPES[t];
      var nm = { type: t, enabled: mod.enabled !== false, title: m.label };
      if (m.hasCount) nm.count = m.def || 1;
      if (m.hasItems) nm.items = [];
      // 切换类型时重置为新类型的默认接口参数
      if (PARAM_SCHEMA[t]) {
        nm.params = {};
        PARAM_SCHEMA[t].forEach(function (f) { nm.params[f.key] = f.default || ""; });
      }
      state.modules[idx] = nm;
      renderCanvas(); renderModuleModal(body, idx);
    });
    body.appendChild(fieldRow("类型", typeSel));

    var title = el("input", { value: mod.title || "" });
    title.addEventListener("input", function () { mod.title = title.value; renderCanvas(); });
    body.appendChild(fieldRow("标题", title));

    if (meta.hasCount) {
      var count = el("input", { type: "number", min: "1", max: "30", value: String(mod.count || meta.def || 1) });
      count.addEventListener("input", function () { mod.count = Number(count.value) || 1; renderCanvas(); });
      body.appendChild(fieldRow("条数", count));
    }
    if (meta.hasItems) {
      if (!Array.isArray(mod.items)) mod.items = [];
      body.appendChild(el("div", { class: "f-label", text: "倒计时条目" }));
      var list = el("div", { class: "f-list" });
      mod.items.forEach(function (it, i) {
        var name = el("input", { class: "grow", value: it.name || "" });
        name.addEventListener("input", function () { it.name = name.value; renderCanvas(); });
        var date = el("input", { class: "grow", value: it.date || "", placeholder: "YYYY-MM-DD 或 MM-DD" });
        date.addEventListener("input", function () { it.date = date.value; renderCanvas(); });
        list.appendChild(el("div", { class: "f-item" }, [
          name, date,
          el("button", {
            class: "btn btn-mini btn-danger", type: "button", text: "✕",
            onclick: function () { mod.items.splice(i, 1); renderCanvas(); renderModuleModal(body, idx); },
          }),
        ]));
      });
      body.appendChild(list);
      body.appendChild(el("button", {
        class: "btn", type: "button", text: "＋ 添加条目",
        onclick: function () { mod.items.push({ name: "新倒计时", date: "2027-01-01" }); renderCanvas(); renderModuleModal(body, idx); },
      }));
    }

    renderApiConfigSection(body, mod);

    body.appendChild(el("div", { class: "f-row" }, [
      el("button", {
        class: "btn btn-mini", type: "button", text: "↑ 上移",
        onclick: function () { move(state.modules, idx, -1); renderCanvas(); renderModuleModal(body, Math.max(0, idx - 1)); },
      }),
      el("button", {
        class: "btn btn-mini", type: "button", text: "↓ 下移",
        onclick: function () { move(state.modules, idx, 1); renderCanvas(); renderModuleModal(body, Math.min(state.modules.length - 1, idx + 1)); },
      }),
      el("button", {
        class: "btn btn-danger", type: "button", text: "删除此模块",
        onclick: function () { state.modules.splice(idx, 1); saveSilent(); closeModal(); renderCanvas(); },
      }),
    ]));
  }

  function addModule() {
    var types = Object.keys(MODULE_TYPES);
    var first = types[0];
    var m = MODULE_TYPES[first];
    var mod = { type: first, enabled: true, title: m.label };
    if (m.hasCount) mod.count = m.def || 1;
    if (m.hasItems) mod.items = [];
    if (PARAM_SCHEMA[first]) {
      mod.params = {};
      PARAM_SCHEMA[first].forEach(function (f) { mod.params[f.key] = f.default || ""; });
    }
    state.modules.push(mod);
    renderCanvas();
    openModal({ kind: "module", index: state.modules.length - 1 });
  }

  // ===== 真实预览 =====
  async function renderPreview(button) {
    var pm = document.getElementById("preview-modal");
    var status = document.getElementById("preview-status");
    var img = document.getElementById("preview-image");
    status.textContent = "正在真实请求接口并渲染…（约 10-30 秒）";
    status.className = "preview-status";
    img.className = "preview-image hidden";
    pm.classList.remove("hidden");
    if (button) { button.disabled = true; }
    try {
      await bridge.apiPost("modules/save", snapshot());
      var data = await bridge.apiPost("preview", {});
      if (!data || !data.image) throw new Error("返回缺少图片");
      img.src = data.image; img.className = "preview-image";
      status.textContent = "渲染完成";
    } catch (e) {
      status.textContent = "预览失败: " + (e && e.message ? e.message : e);
    } finally {
      if (button) { button.disabled = false; }
    }
  }
  function closePreview() { document.getElementById("preview-modal").classList.add("hidden"); }

  // ===== 数据 =====
  async function loadConfig() {
    var data = await bridge.apiGet("modules");
    state = {
      moyu_title: data.moyu_title || "摸鱼日历",
      moyu_items: Array.isArray(data.moyu_items) ? data.moyu_items : [],
      history_enabled: data.history_enabled !== false,
      history_title: data.history_title || "历史上的今天",
      history_count: Number(data.history_count) || 4,
      top_source: data.top_source || "history",
      mid1_source: data.mid1_source || "anime",
      mid1_title: data.mid1_title || "今日新番",
      mid1_count: Number(data.mid1_count) || 4,
      mid1_params: data.mid1_params && typeof data.mid1_params === "object" ? data.mid1_params : {},
      mid2_source: data.mid2_source || "news",
      mid2_title: data.mid2_title || "60s读懂世界",
      mid2_count: Number(data.mid2_count) || 10,
      mid2_params: data.mid2_params && typeof data.mid2_params === "object" ? data.mid2_params : {},
      exchange_from: data.exchange_from || "USD",
      exchange_to: data.exchange_to || "CNY",
      exchange_amount: Number(data.exchange_amount) || 100,
      quote_enabled: data.quote_enabled !== false,
      quote_title: data.quote_title || "",
      quote_sources:
        Array.isArray(data.quote_sources) && data.quote_sources.length
          ? data.quote_sources
          : ["hitokoto"],
      modules: Array.isArray(data.modules) ? data.modules : [],
    };
    renderCanvas();
  }
  function saveSilent() {
    if (!bridge) return;
    bridge.apiPost("modules/save", snapshot()).catch(function (e) {
      msg("自动保存失败: " + (e && e.message ? e.message : e), true);
    });
  }
  async function saveConfig(button) {
    if (button) { button.disabled = true; }
    try {
      await bridge.apiPost("modules/save", snapshot());
      msg("配置已保存，日报下次生成时生效");
    } catch (e) {
      msg("保存失败: " + (e && e.message ? e.message : e), true);
    } finally {
      if (button) { button.disabled = false; }
    }
  }

  window.addEventListener("DOMContentLoaded", async function () {
    document.getElementById("btn-save").addEventListener("click", function (e) { saveConfig(e.currentTarget); });
    document.getElementById("btn-preview").addEventListener("click", function (e) { renderPreview(e.currentTarget); });
    document.getElementById("btn-reload").addEventListener("click", function () {
      loadConfig().catch(function (e) { msg(e.message, true); });
    });
    document.getElementById("modal").addEventListener("click", function (e) {
      if (e.target && e.target.hasAttribute && e.target.hasAttribute("data-close-modal")) closeModal();
    });
    document.getElementById("preview-modal").addEventListener("click", function (e) {
      if (e.target && e.target.hasAttribute && e.target.hasAttribute("data-close-preview")) closePreview();
    });
    window.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        if (!document.getElementById("modal").classList.contains("hidden")) closeModal();
        if (!document.getElementById("preview-modal").classList.contains("hidden")) closePreview();
      }
    });

    try {
      bridge = await resolveBridge();
      try {
        var meta = await bridge.apiGet("meta");
        if (meta && meta.module_types) {
          var backendTypes = {};
          Object.keys(meta.module_types).forEach(function (key) {
            var info = meta.module_types[key] || {};
            backendTypes[key] = {
              label: info.title || MODULE_TYPES[key] && MODULE_TYPES[key].label || key,
              hasCount: Boolean(info.has_count),
              hasItems: Boolean(info.has_items),
              def: Number(info.count) || (MODULE_TYPES[key] && MODULE_TYPES[key].def) || 1,
            };
          });
          MODULE_TYPES = Object.assign({}, MODULE_TYPES, backendTypes);
        }
        if (meta && meta.quote_sources) QUOTE_SOURCES = meta.quote_sources;
        if (meta && meta.param_schema) PARAM_SCHEMA = meta.param_schema;
        if (meta && meta.top_sources) TOP_SOURCES = meta.top_sources;
        if (meta && meta.mid1_sources) MID1_SOURCES = meta.mid1_sources;
        if (meta && meta.mid2_sources) MID2_SOURCES = meta.mid2_sources;
      } catch (e) {}
      await loadConfig();
    } catch (e) {
      msg((e && e.message ? e.message : e) + "（仍可本地编辑画布）", true);
      renderCanvas();
    }
  });
})();

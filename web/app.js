"use strict";

const state = {
  view: "pending",
  page: 1,
  pageSize: 10,
  totalPages: 1,
  pendingCount: 0,
  groups: [],
  loading: true,
  settingsOpen: false,
  toastTimer: null,
  listSeq: 0, // 列表请求序号：旧响应到达时丢弃，防止竞态覆盖
};

const TOKEN_KEY = "qjk_token";

const $ = (id) => document.getElementById(id);

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function setToken(v) {
  if (v) localStorage.setItem(TOKEN_KEY, v);
  else localStorage.removeItem(TOKEN_KEY);
}

async function api(path, options) {
  const headers = { ...(options && options.headers) };
  const token = getToken();
  if (token) headers["X-QJK-Token"] = token;
  const resp = await fetch(path, { ...options, headers });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "请求失败" }));
    const e = new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
    e.status = resp.status;
    throw e;
  }
  return resp.json();
}

function post(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

/* ── 时间格式化 ── */
function fmtTime(isoStr) {
  const t = new Date(isoStr.replace(" ", "T"));
  if (isNaN(t)) return isoStr;
  const diff = (Date.now() - t.getTime()) / 1000;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  const now = new Date();
  const sameYear = t.getFullYear() === now.getFullYear();
  const pad = (n) => String(n).padStart(2, "0");
  return sameYear ? `${t.getMonth() + 1}月${t.getDate()}日 ${pad(t.getHours())}:${pad(t.getMinutes())}`
                  : `${t.getFullYear()}年${t.getMonth() + 1}月${t.getDate()}日`;
}

/* ── 列表渲染 ── */
function groupByStation(items) {
  const groups = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last && last.station === item.station) {
      // 同站同码（跨日重复 / 手动+短信并存）合并为一条显示，操作作用于全部 id
      const twin = last.items.find((p) => p.pickup_code === item.pickup_code);
      if (twin) twin.ids.push(item.id);
      else {
        item.ids = [item.id];
        last.items.push(item);
      }
    } else {
      item.ids = [item.id];
      groups.push({ station: item.station, items: [item] });
    }
  }
  return groups;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function render() {
  $("settings-view").hidden = !state.settingsOpen;
  $("badge").textContent = state.pendingCount > 0 ? `${state.pendingCount} 件未取` : "";
  document.querySelectorAll("#tabs .tab").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === state.view);
  });

  const list = $("list-view");
  if (state.settingsOpen) {
    list.innerHTML = "";
    return;
  }
  if (state.loading) {
    list.innerHTML = `<div class="empty">加载中…</div>`;
    return;
  }
  if (state.groups.length === 0) {
    list.innerHTML = `<div class="empty">${
      state.view === "pending" ? "暂无未取包裹，取件码到达后会自动出现" : "暂无已取记录"
    }</div>`;
    return;
  }

  let html = "";
  for (const g of state.groups) {
    html += `<section class="station-group">
      <div class="station-header ${state.view === "collected" ? "collected" : ""}">
        <span class="dot"></span>${esc(g.station)}
      </div>`;
    for (const pkg of g.items) {
      const meta = [esc(fmtTime(pkg.received_at)), pkg.express ? `<span class="express-tag">${esc(pkg.express)}</span>` : ""]
        .filter(Boolean).join("");
      const ids = pkg.ids.join(",");
      const action = state.view === "pending"
        ? `<button class="btn btn-primary" data-action="collect" data-ids="${ids}">已取</button>`
        : `<button class="btn btn-ghost" data-action="uncollect" data-ids="${ids}">撤销</button>`;
      html += `<article class="package ${pkg.status === "collected" ? "collected" : ""}">
        <div class="package-main">
          <div class="code">${esc(pkg.pickup_code)}${state.view === "collected" ? '<span class="code-status">已取</span>' : ""}</div>
          <div class="package-meta">${meta}</div>
        </div>
        <div class="package-actions">${action}
          <button class="btn btn-ghost btn-danger" data-action="delete" data-ids="${ids}">删除</button>
        </div>
      </article>`;
    }
    html += `</section>`;
  }
  if (state.totalPages > 1) {
    html += `<div class="pager">
      <button data-action="page" data-delta="-1" ${state.page <= 1 ? "disabled" : ""}>上一页</button>
      <span>${state.page} / ${state.totalPages}</span>
      <button data-action="page" data-delta="1" ${state.page >= state.totalPages ? "disabled" : ""}>下一页</button>
    </div>`;
  }
  list.innerHTML = html;
}

/* ── 数据加载 ── */
async function refreshPendingCount() {
  try {
    const data = await api(`/api/packages?status=pending&page=1&page_size=1`);
    state.pendingCount = data.total;
    render();
  } catch { /* 忽略，下次轮询重试 */ }
}

async function loadList() {
  const seq = ++state.listSeq;
  while (true) {
    state.loading = true;
    render();
    try {
      const data = await api(`/api/packages?status=${state.view}&page=${state.page}&page_size=${state.pageSize}`);
      if (seq !== state.listSeq) return; // 已有更新的请求，丢弃本次结果
      // 删除/标记后当前页可能为空：回退到存在的最后一页
      if (data.pages > 0 && state.page > data.pages) {
        state.page = data.pages;
        continue;
      }
      state.loading = false;
      state.totalPages = data.pages;
      state.groups = groupByStation(data.items);
    } catch (e) {
      if (seq !== state.listSeq) return;
      state.loading = false;
      state.groups = [];
      if (e.status === 401 && !getToken()) { openSettings(true); return; } // 首次访问引导填口令
      showToast(`加载失败：${e.message}`);
    }
    break;
  }
  render();
  refreshPendingCount();
}

function switchView(view) {
  if (state.view === view && !state.settingsOpen) return;
  state.view = view;
  state.page = 1;
  state.settingsOpen = false;
  loadList();
}

function goPage(delta) {
  const next = state.page + delta;
  if (next < 1 || next > state.totalPages) return;
  state.page = next;
  loadList();
}

/* ── 操作 ── */
async function markCollected(ids) {
  try {
    for (const id of ids) await post(`/api/packages/${id}/collected`);
    await loadList();
  } catch (e) { showToast(e.message); }
}

async function markPending(ids) {
  try {
    for (const id of ids) await post(`/api/packages/${id}/pending`);
    await loadList();
  } catch (e) { showToast(e.message); }
}

async function deletePackage(ids) {
  if (!confirm(`确定删除这 ${ids.length > 1 ? `${ids.length} 条` : "条"}记录吗？删除后不可恢复。`)) return;
  try {
    for (const id of ids) await api(`/api/packages/${id}`, { method: "DELETE" });
    showToast("已删除");
    await loadList();
  } catch (e) { showToast(e.message); }
}

function openAdd() {
  $("add-station").value = "";
  $("add-code").value = "";
  $("add-overlay").hidden = false;
}

async function submitAdd() {
  const station = $("add-station").value.trim();
  const pickupCode = $("add-code").value.trim();
  if (!station || !pickupCode) { showToast("请填写驿站名和取件码"); return; }
  try {
    const r = await post("/api/packages", { station, pickup_code: pickupCode });
    $("add-overlay").hidden = true;
    showToast(r.duplicated ? "该取件码已存在" : "已添加");
    await loadList();
  } catch (e) { showToast(e.message); }
}

/* ── 设置 ── */
async function openSettings(focusToken = false) {
  state.settingsOpen = true;
  render();
  try {
    const s = await api("/api/settings");
    if (!$("bark-key").value) $("bark-key").value = s.bark_key || "";
  } catch (e) { showToast(`设置加载失败：${e.message}`); }
  if (!$("access-token").value) $("access-token").value = getToken();
  if (focusToken && !getToken()) $("access-token").focus();
}

async function saveSettings() {
  const barkKey = $("bark-key").value.trim();
  try {
    await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bark_key: barkKey }),
    });
    return true;
  } catch (e) {
    showToast(`保存失败：${e.message}`);
    return false;
  }
}

async function saveToken() {
  setToken($("access-token").value.trim());
  showToast("访问口令已保存");
}

async function testNotify() {
  if (!(await saveSettings())) return;
  try {
    await post("/api/notify/test");
    showToast("测试提醒已发送，请查看手机");
  } catch (e) { showToast(e.message); }
}

function showToast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { el.hidden = true; }, 2500);
}

/* ── 事件 ── */
document.getElementById("app").addEventListener("click", (e) => {
  const el = e.target.closest("[data-action], [data-tab]");
  if (!el) return;
  const action = el.dataset.action;
  const tab = el.dataset.tab;
  if (tab) { switchView(tab); return; }
  switch (action) {
    case "open-add": openAdd(); break;
    case "close-add": $("add-overlay").hidden = true; break;
    case "submit-add": submitAdd(); break;
    case "open-settings": openSettings(); break;
    case "test-notify": testNotify(); break;
    case "collect": markCollected(el.dataset.ids.split(",").map(Number)); break;
    case "uncollect": markPending(el.dataset.ids.split(",").map(Number)); break;
    case "delete": deletePackage(el.dataset.ids.split(",").map(Number)); break;
    case "page": goPage(Number(el.dataset.delta)); break;
  }
});

$("bark-key").addEventListener("blur", saveSettings);
$("access-token").addEventListener("blur", saveToken);
$("add-overlay").addEventListener("click", (e) => {
  if (e.target === $("add-overlay")) $("add-overlay").hidden = true;
});

/* PWA 注册 */
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

/* 启动：立即加载 + 30 秒轮询 */
loadList();
setInterval(loadList, 30000);
setInterval(refreshPendingCount, 30000);

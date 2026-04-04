"""FastAPI routes: dashboard HTML + JSON snapshot API."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import HTTPException, Query

from adktelemetry.finops import list_known_models
from adktelemetry.store import TelemetryStore

_MAX_RANGE_SEC = 31 * 86400

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AdkTelemetry - Dashboard</title>
  <style>
    :root {
      --bg: #ffffff;
      --border: #e5e7eb;
      --text: #111827;
      --muted: #6b7280;
      --accent: #2563eb;
      --card-shadow: 0 1px 3px rgba(0,0,0,.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 24px;
      border-bottom: 1px solid var(--border);
    }
    header h1 { font-size: 1.25rem; margin: 0; font-weight: 700; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .pill {
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 0.8rem;
      background: #f9fafb;
      color: var(--muted);
    }
    main {
      padding: 20px 24px 48px;
      max-width: 1400px;
      margin: 0 auto;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 16px;
    }
    .card {
      grid-column: span 12;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      background: #fff;
      box-shadow: var(--card-shadow);
    }
    @media (min-width: 900px) {
      .card.span-4 { grid-column: span 4; }
      .card.span-6 { grid-column: span 6; }
      .card.span-8 { grid-column: span 8; }
    }
    .card-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .card-title { font-size: 0.95rem; font-weight: 600; }
    .muted { color: var(--muted); font-size: 0.85rem; }
    .donut-wrap { display: flex; flex-wrap: wrap; align-items: center; gap: 20px; justify-content: center; }
    .donut {
      width: 160px; height: 160px; border-radius: 50%;
      background: conic-gradient(
        #22c55e 0% 28%, #3b82f6 28% 52%, #f97316 52% 72%, #ec4899 72% 88%, #a855f7 88% 100%
      );
      mask: radial-gradient(circle 55px at center, transparent 98%, #000 100%);
      -webkit-mask: radial-gradient(circle 55px at center, transparent 98%, #000 100%);
    }
    .legend { display: flex; flex-direction: column; gap: 6px; font-size: 0.8rem; }
    .legend span { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
    .bars { display: flex; flex-direction: column; gap: 10px; }
    .bar-row { display: grid; grid-template-columns: 120px 1fr 64px; gap: 8px; align-items: center; font-size: 0.8rem; min-height: 1.5rem; }
    .bar-track { background: #f3f4f6; border-radius: 4px; height: 10px; overflow: hidden; }
    .cost-session-inner { display: flex; flex-direction: column; min-height: 0; }
    .cost-session-scroll {
      max-height: calc(7 * (1.5rem + 10px) + 6 * 10px);
      overflow-y: auto;
      overflow-x: hidden;
      padding-right: 4px;
      margin: 0 -4px 0 0;
    }
    .cost-session-scroll::-webkit-scrollbar { width: 8px; }
    .cost-session-scroll::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 4px; }
    .cost-session-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--border);
      font-size: 0.85rem;
      font-weight: 600;
      flex-shrink: 0;
    }
    .cost-session-footer .muted { font-weight: 500; }
    .cost-session-footer .total { font-variant-numeric: tabular-nums; color: var(--text); }
    .bar-fill { height: 100%; background: var(--accent); border-radius: 4px; width: 0%; transition: width .4s ease; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 500; }
    .ts-chart { height: 140px; display: flex; align-items: flex-end; gap: 3px; }
    .ts-bar { flex: 1; background: linear-gradient(#fbbf24, #3b82f6); border-radius: 2px 2px 0 0; min-height: 4px; }
    .line-chart { height: 120px; position: relative; border-left: 1px solid var(--border); border-bottom: 1px solid var(--border); }
    .line-chart svg { width: 100%; height: 100%; }
    footer { padding: 16px 24px; color: var(--muted); font-size: 0.75rem; border-top: 1px solid var(--border); }
    a { color: var(--accent); }
    .pill.err { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
    .table-scroll {
      overflow-x: auto;
      overflow-y: auto;
      padding-right: 4px;
      margin: 0 -4px 0 0;
    }
    .table-scroll::-webkit-scrollbar { width: 8px; height: 8px; }
    .table-scroll::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 4px; }
    .table-scroll thead th {
      position: sticky;
      top: 0;
      z-index: 2;
      background: #fff;
      box-shadow: 0 1px 0 var(--border);
    }
    .table-scroll--errors {
      max-height: calc(2.5rem + 4 * 3rem);
    }
    .table-scroll--sessions {
      max-height: calc(2.5rem + 10 * 2.5rem);
    }
    table.err-table td, table.err-table th { font-size: 0.78rem; vertical-align: top; }
    table.err-table td.msg { color: #374151; max-width: min(520px, 40vw); word-break: break-word; }
    table.err-table code { font-size: 0.72rem; background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }
    tr.session-has-errors td { background: #fffbeb; }
    .range-wrap { position: relative; }
    .range-trigger {
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 0.8rem;
      background: #f9fafb;
      color: var(--muted);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-family: inherit;
    }
    .range-trigger:hover { background: #f3f4f6; }
    .range-trigger[aria-expanded="true"] { border-color: #93c5fd; box-shadow: 0 0 0 1px #bfdbfe; }
    .range-chevron { font-size: 0.65rem; opacity: 0.7; }
    .range-panel {
      display: none;
      position: absolute;
      right: 0;
      top: calc(100% + 6px);
      min-width: 240px;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: 0 8px 24px rgba(0,0,0,.12);
      padding: 6px;
      z-index: 100;
    }
    .range-panel.open { display: block; }
    .range-opt {
      display: block;
      width: 100%;
      text-align: left;
      padding: 8px 10px;
      border: none;
      background: transparent;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.85rem;
      color: var(--text);
      font-family: inherit;
    }
    .range-opt:hover { background: #f3f4f6; }
    .range-custom {
      margin-top: 4px;
      padding-top: 8px;
      border-top: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .range-custom label { font-size: 0.78rem; color: var(--muted); display: flex; flex-direction: column; gap: 4px; }
    .range-custom input[type="date"] {
      font-size: 0.85rem;
      padding: 6px 8px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-family: inherit;
    }
    .range-apply {
      margin-top: 4px;
      padding: 8px 12px;
      border-radius: 8px;
      border: none;
      background: var(--accent);
      color: #fff;
      font-size: 0.85rem;
      cursor: pointer;
      font-family: inherit;
    }
    .range-apply:hover { filter: brightness(1.05); }
    .range-err { font-size: 0.75rem; color: #b91c1c; min-height: 1.2em; }
  </style>
</head>
<body>
  <header>
    <h1>AdkTelemetry</h1>
    <div class="toolbar">
      <span class="pill" id="pill-sessions">Sessions -</span>
      <span class="pill err" id="pill-errors">Errors -</span>
      <span class="pill" id="pill-models">Models in catalog -</span>
      <div class="range-wrap" id="range-wrap">
        <button type="button" class="range-trigger" id="range-trigger" aria-expanded="false" aria-haspopup="listbox">
          <span id="range-label">Last 15 minutes</span>
          <span class="range-chevron" aria-hidden="true">▾</span>
        </button>
        <div class="range-panel" id="range-panel" role="listbox">
          <button type="button" class="range-opt" data-preset="15m" role="option">15 minutes</button>
          <button type="button" class="range-opt" data-preset="30m" role="option">30 minutes</button>
          <button type="button" class="range-opt" data-preset="1h" role="option">1 hour</button>
          <button type="button" class="range-opt" data-preset="12h" role="option">12 hours</button>
          <div class="range-custom" id="range-custom">
            <span class="muted" style="font-size:0.78rem">Custom range (max 31 days)</span>
            <label>Start date <input type="date" id="range-start-date" /></label>
            <label>End date <input type="date" id="range-end-date" /></label>
            <p class="muted" style="margin:0;font-size:0.72rem">Uses local timezone (start 00:00, end 23:59:59).</p>
            <button type="button" class="range-apply" id="range-apply-custom">Apply range</button>
            <div class="range-err" id="range-custom-err"></div>
          </div>
        </div>
      </div>
    </div>
  </header>
  <main>
    <p class="muted" style="margin-top:0">AdkTelemetry - observability for Google ADK agents (events, tokens, FinOps). Data updates every few seconds.</p>
    <div class="grid">
      <section class="card span-4">
        <div class="card-head"><span class="card-title">Invocations by model</span></div>
        <div class="donut-wrap">
          <div class="donut" aria-hidden="true"></div>
          <div class="legend" id="model-legend"></div>
        </div>
      </section>
      <section class="card span-4">
        <div class="card-head"><span class="card-title">ADK events (Runner)</span></div>
        <div class="bars" id="bar-sources"></div>
      </section>
      <section class="card span-4">
        <div class="card-head"><span class="card-title">Estimated cost by session (USD)</span></div>
        <div class="cost-session-inner">
          <div class="cost-session-scroll bars" id="bar-cost-scroll"></div>
          <div class="cost-session-footer">
            <span class="muted">Total cost (all sessions)</span>
            <span class="total" id="cost-sessions-total">0.000000</span>
          </div>
        </div>
      </section>
      <section class="card span-8">
        <div class="card-head"><span class="card-title">Activity timeline (stacked)</span></div>
        <div class="ts-chart" id="ts-chart"></div>
        <p class="muted" style="margin-bottom:0">Synthetic buckets from event counts in the selected time range.</p>
      </section>
      <section class="card span-4">
        <div class="card-head"><span class="card-title">Token trend (in + out)</span></div>
        <div class="line-chart"><svg viewBox="0 0 200 100" preserveAspectRatio="none" id="line-svg"></svg></div>
      </section>
      <section class="card span-12">
        <div class="card-head"><span class="card-title">Sessions Errors</span></div>
        <p class="muted" style="margin-top:0">Per session: native <code>LlmResponse</code> fields and failures surfaced as plain text on model or system events. The <strong>Errors</strong> column in the Sessions table uses the same count.</p>
        <div class="table-scroll table-scroll--errors">
          <table class="err-table">
            <thead><tr><th>Time</th><th>Session</th><th>Author</th><th>Code</th><th>Message</th></tr></thead>
            <tbody id="error-rows"></tbody>
          </table>
        </div>
      </section>
      <section class="card span-12">
        <div class="card-head"><span class="card-title">Sessions</span></div>
        <div class="table-scroll table-scroll--sessions">
          <table>
            <thead><tr><th>Session</th><th>User</th><th>Events</th><th>Errors</th><th>In tok</th><th>Out tok</th><th>Cost USD</th></tr></thead>
            <tbody id="session-rows"></tbody>
          </table>
        </div>
      </section>
    </div>
  </main>
  <footer>
    FinOps rates ship with the library (<code>adktelemetry/gemini_pricing.yaml</code>). Update each release from
    <a href="https://ai.google.dev/gemini-api/docs/pricing?hl=pt-br" target="_blank" rel="noopener">Gemini API pricing</a>.
  </footer>
  <script>
    // Caminho absoluto: com URL /adktelemetry (sem barra final), "./api/..." virava /api/... (404).
    const API = "/adktelemetry/api/v1/snapshot";
    const colors = ["#22c55e","#3b82f6","#f97316","#ec4899","#a855f7","#14b8a6"];
    const RANGE_LABELS = { "15m": "Last 15 minutes", "30m": "Last 30 minutes", "1h": "Last 1 hour", "12h": "Last 12 hours" };
    let rangePreset = "15m";
    let useCustomRange = false;
    let customSinceSec = 0;
    let customUntilSec = 0;

    function snapshotQuery() {
      const until = Date.now() / 1000;
      if (useCustomRange) {
        return "since=" + encodeURIComponent(customSinceSec) + "&until=" + encodeURIComponent(customUntilSec);
      }
      const mins = { "15m": 15, "30m": 30, "1h": 60, "12h": 720 }[rangePreset] || 15;
      const since = until - mins * 60;
      return "since=" + encodeURIComponent(since) + "&until=" + encodeURIComponent(until);
    }

    function updateRangeLabel() {
      const el = document.getElementById("range-label");
      if (!el) return;
      if (useCustomRange) {
        const a = new Date(customSinceSec * 1000);
        const b = new Date(customUntilSec * 1000);
        const f = (d) =>
          (d.getMonth() + 1).toString().padStart(2, "0") +
          "/" +
          d.getDate().toString().padStart(2, "0") +
          "/" +
          d.getFullYear();
        el.textContent = f(a) + " – " + f(b);
      } else {
        el.textContent = RANGE_LABELS[rangePreset] || RANGE_LABELS["15m"];
      }
    }

    function closeRangePanel() {
      const p = document.getElementById("range-panel");
      const t = document.getElementById("range-trigger");
      if (p) p.classList.remove("open");
      if (t) t.setAttribute("aria-expanded", "false");
    }

    function openRangePanel() {
      const p = document.getElementById("range-panel");
      const t = document.getElementById("range-trigger");
      if (p) p.classList.add("open");
      if (t) t.setAttribute("aria-expanded", "true");
    }

    document.getElementById("range-trigger").addEventListener("click", function (ev) {
      ev.stopPropagation();
      const p = document.getElementById("range-panel");
      if (p && p.classList.contains("open")) closeRangePanel();
      else openRangePanel();
    });

    document.querySelectorAll(".range-opt[data-preset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        rangePreset = btn.getAttribute("data-preset") || "15m";
        useCustomRange = false;
        updateRangeLabel();
        closeRangePanel();
        refresh();
      });
    });

    document.getElementById("range-apply-custom").addEventListener("click", function () {
      const errEl = document.getElementById("range-custom-err");
      errEl.textContent = "";
      const sv = document.getElementById("range-start-date").value;
      const ev = document.getElementById("range-end-date").value;
      if (!sv || !ev) {
        errEl.textContent = "Select start and end dates.";
        return;
      }
      const sp = sv.split("-").map(Number);
      const ep = ev.split("-").map(Number);
      const startMs = new Date(sp[0], sp[1] - 1, sp[2], 0, 0, 0, 0).getTime();
      const endMs = new Date(ep[0], ep[1] - 1, ep[2], 23, 59, 59, 999).getTime();
      if (startMs > endMs) {
        errEl.textContent = "Start date must be on or before end date.";
        return;
      }
      const spanSec = (endMs - startMs) / 1000;
      if (spanSec > 31 * 86400) {
        errEl.textContent = "Range cannot exceed 31 days.";
        return;
      }
      useCustomRange = true;
      customSinceSec = startMs / 1000;
      customUntilSec = endMs / 1000;
      updateRangeLabel();
      closeRangePanel();
      refresh();
    });

    document.addEventListener("click", function () {
      closeRangePanel();
    });
    document.getElementById("range-panel").addEventListener("click", function (ev) {
      ev.stopPropagation();
    });

    function maxObj(obj) {
      const vals = Object.values(obj||{}).map(Number);
      return Math.max(1, ...vals);
    }

    function setDonutFromDistribution(dist) {
      const el = document.querySelector(".donut");
      if (!el) return;
      const entries = Object.entries(dist || {}).slice(0, 8);
      if (!entries.length) {
        el.style.background = "conic-gradient(#e5e7eb 0% 100%)";
        return;
      }
      const total = entries.reduce((a, [, v]) => a + Number(v), 0) || 1;
      let acc = 0;
      const stops = entries.map(([_, v], i) => {
        const pct = (Number(v) / total) * 100;
        const start = acc;
        acc += pct;
        return colors[i % colors.length] + " " + start + "% " + acc + "%";
      });
      el.style.background = "conic-gradient(" + stops.join(", ") + ")";
    }

    function appendBarRow(container, label, value, maxVal) {
      const row = document.createElement("div");
      row.className = "bar-row";
      const pct = Math.round(100 * (Number(value) || 0) / maxVal);
      row.innerHTML =
        '<div></div><div class="bar-track"><div class="bar-fill" style="width:' +
        pct +
        '%"></div></div><div></div>';
      row.children[0].textContent = label;
      row.children[2].textContent = String(value);
      container.appendChild(row);
    }

    function appendSessionRow(tbody, s) {
      const tr = document.createElement("tr");
      if (Number(s.error_count) > 0) tr.className = "session-has-errors";
      const cells = [
        s.session_id,
        s.user_id,
        s.event_count,
        s.error_count,
        s.total_input_tokens,
        s.total_output_tokens,
        (s.total_cost_usd != null ? Number(s.total_cost_usd).toFixed(6) : "0"),
      ];
      cells.forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text == null ? "" : String(text);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    }

    function appendErrorRow(tbody, e) {
      const tr = document.createElement("tr");
      const ts = e.ts != null ? String(e.ts) : "-";
      const sid = (e.session_id || "").slice(0, 14) + (e.session_id && e.session_id.length > 14 ? "…" : "");
      const msg = (e.error_message || "").slice(0, 400);
      const cells = [ts, sid, e.author || "-", e.error_code || "-", msg];
      cells.forEach((text, i) => {
        const td = document.createElement("td");
        if (i === 1 && e.session_id) td.title = e.session_id;
        if (i === 4) td.className = "msg";
        td.textContent = text == null ? "" : String(text);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    }

    async function refresh() {
      try {
        const r = await fetch(API + "?" + snapshotQuery(), { cache: "no-store" });
        if (!r.ok) throw new Error("snapshot HTTP " + r.status);
        const data = await r.json();

        document.getElementById("pill-sessions").textContent =
          "Sessions " + (data.totals && data.totals.sessions != null ? data.totals.sessions : 0);
        document.getElementById("pill-models").textContent =
          "Pricing models " + (data.pricing_models != null ? data.pricing_models : 0);
        document.getElementById("pill-errors").textContent =
          "Errors " + (data.totals && data.totals.errors != null ? data.totals.errors : 0);

        const dist = data.model_distribution || {};
        setDonutFromDistribution(dist);

        const leg = document.getElementById("model-legend");
        leg.textContent = "";
        Object.entries(dist).slice(0, 8).forEach(([k, v], i) => {
          const row = document.createElement("div");
          const sw = document.createElement("span");
          sw.style.cssText =
            "display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;background:" +
            colors[i % colors.length];
          row.appendChild(sw);
          row.appendChild(document.createTextNode(k + " - " + v));
          leg.appendChild(row);
        });

        const events = (data.totals && data.totals.events) || 0;
        const src = { adk: events };
        const smax = maxObj(src);
        const bs = document.getElementById("bar-sources");
        bs.textContent = "";
        Object.entries(src).forEach(([k, v]) => appendBarRow(bs, k, v, smax));

        const sessions = Array.isArray(data.sessions) ? data.sessions : [];
        const costs = sessions.map((s) => Number(s.total_cost_usd) || 0);
        const totalSessionCost = costs.reduce((sum, v) => sum + v, 0);
        const cmax = Math.max(1e-12, ...costs, 1);
        const bc = document.getElementById("bar-cost-scroll");
        bc.textContent = "";
        sessions.forEach((s) => {
          const row = document.createElement("div");
          row.className = "bar-row";
          const pct = Math.round((100 * (Number(s.total_cost_usd) || 0)) / cmax);
          const sid = (s.session_id || "").slice(0, 22);
          row.innerHTML =
            '<div class="sid"></div><div class="bar-track"><div class="bar-fill" style="width:' +
            pct +
            '%"></div></div><div class="cost"></div>';
          row.querySelector(".sid").textContent = sid;
          row.querySelector(".sid").title = s.session_id || "";
          row.querySelector(".cost").textContent = (Number(s.total_cost_usd) || 0).toFixed(6);
          bc.appendChild(row);
        });
        const totalEl = document.getElementById("cost-sessions-total");
        if (totalEl) totalEl.textContent = totalSessionCost.toFixed(6);

        const erb = document.getElementById("error-rows");
        erb.textContent = "";
        const errs = Array.isArray(data.recent_errors) ? data.recent_errors : [];
        if (!errs.length) {
          const tr = document.createElement("tr");
          const td = document.createElement("td");
          td.colSpan = 5;
          td.className = "muted";
          td.textContent = "No errors recorded yet.";
          tr.appendChild(td);
          erb.appendChild(tr);
        } else {
          errs.slice(0, 40).forEach((e) => appendErrorRow(erb, e));
        }

        const tb = document.getElementById("session-rows");
        tb.textContent = "";
        sessions.slice(0, 50).forEach((s) => appendSessionRow(tb, s));

        const n = 24;
        const chart = document.getElementById("ts-chart");
        chart.textContent = "";
        const totalEv = events;
        for (let i = 0; i < n; i++) {
          const wave = 0.55 + 0.45 * Math.sin((i / n) * Math.PI * 2);
          const bucket = totalEv > 0 ? (totalEv / n) * (0.7 + 0.6 * wave) : 5 * wave;
          const h = Math.min(95, Math.max(6, (bucket / Math.max(totalEv / n, 1)) * 55));
          const d = document.createElement("div");
          d.className = "ts-bar";
          d.style.height = h + "%";
          d.title = "bucket ~" + Math.round(bucket) + " events";
          chart.appendChild(d);
        }

        const svg = document.getElementById("line-svg");
        const ordered = sessions.slice().sort((a, b) => (b.last_timestamp || 0) - (a.last_timestamp || 0));
        const ptsIn = ordered.slice(0, 14).map((s, i) => ({ x: i, y: Number(s.total_input_tokens) || 0 }));
        const ptsOut = ordered.slice(0, 14).map((s, i) => ({ x: i, y: Number(s.total_output_tokens) || 0 }));
        const ymax = Math.max(1, ...ptsIn.map((p) => p.y), ...ptsOut.map((p) => p.y));
        function pathLine(pts) {
          if (!pts.length) return "";
          const n1 = Math.max(pts.length - 1, 1);
          return pts
            .map((p, i) => {
              const x = 8 + (i / n1) * 184;
              const y = 88 - (p.y / ymax) * 72;
              return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
            })
            .join(" ");
        }
        const legend =
          '<text x="4" y="12" font-size="8" fill="#6b7280">in</text><text x="4" y="22" font-size="8" fill="#22c55e">out</text>';
        svg.innerHTML =
          legend +
          '<path d="' +
          pathLine(ptsIn) +
          '" fill="none" stroke="#3b82f6" stroke-width="2" vector-effect="non-scaling-stroke"/>' +
          '<path d="' +
          pathLine(ptsOut) +
          '" fill="none" stroke="#22c55e" stroke-width="2" vector-effect="non-scaling-stroke"/>';
      } catch (e) {
        console.error("AdkTelemetry refresh:", e);
      }
    }
    updateRangeLabel();
    refresh();
    setInterval(refresh, 4000);
  </script>
</body>
</html>
"""


def register_routes(app: Any) -> None:
    """Idempotent: safe if called multiple times."""
    if getattr(app.state, "adktelemetry_registered", False):
        return

    @app.get("/adktelemetry", include_in_schema=False)
    @app.get("/adktelemetry/", include_in_schema=False)
    async def dashboard() -> Any:
        from fastapi.responses import HTMLResponse

        return HTMLResponse(_DASHBOARD_HTML)

    @app.get("/adktelemetry/api/v1/snapshot", include_in_schema=False)
    async def snapshot(
        since: float | None = Query(None, description="Range start (Unix seconds)"),
        until: float | None = Query(None, description="Range end (Unix seconds)"),
    ) -> Any:
        from fastapi.responses import JSONResponse

        from adktelemetry.config import get_config

        cfg = get_config()
        pricing_path = cfg.pricing_config_path if cfg else None
        default_model = cfg.adkmodel if cfg else None

        now = time.time()
        if since is None and until is None:
            snap = TelemetryStore.instance().snapshot()
            snap["applied_range"] = None
        else:
            until_f = float(until) if until is not None else now
            since_f = float(since) if since is not None else (until_f - 15 * 60)
            if since_f >= until_f:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid range: `since` must be less than `until`.",
                )
            if until_f - since_f > _MAX_RANGE_SEC:
                raise HTTPException(
                    status_code=400,
                    detail="Time range cannot exceed 31 days.",
                )
            snap = TelemetryStore.instance().snapshot_filtered(
                since_f,
                until_f,
                default_model=default_model,
                pricing_config_path=pricing_path,
            )
            snap["applied_range"] = {"since": since_f, "until": until_f}

        snap["pricing_models"] = len(list_known_models(pricing_path))
        return JSONResponse(content=json.loads(json.dumps(snap, default=str)))

    app.state.adktelemetry_registered = True

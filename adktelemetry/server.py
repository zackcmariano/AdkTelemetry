"""FastAPI routes: dashboard HTML + JSON snapshot API."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import HTTPException, Query

from adktelemetry.finops import list_known_models, pricing_catalog
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
    button.pill {
      font-family: inherit;
      cursor: pointer;
    }
    button.pill:hover {
      background: #eef2ff;
      border-color: #c7d2fe;
      color: var(--text);
    }
    button.pill:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
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
    .bar-fill.bar-fill--err { background: #ef4444; }
    .bar-fill.bar-fill--tok-in { background: #3b82f6; }
    .bar-fill.bar-fill--tok-out { background: #22c55e; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 500; }
    .ts-chart-block { display: flex; flex-direction: column; gap: 4px; }
    .ts-chart { height: 140px; display: flex; align-items: flex-end; gap: 3px; }
    .ts-bar { flex: 1; background: linear-gradient(#fbbf24, #3b82f6); border-radius: 2px 2px 0 0; min-height: 4px; }
    .ts-chart-axis {
      display: flex;
      flex-direction: row;
      gap: 3px;
      align-items: flex-start;
      min-height: 2.4rem;
      padding: 0 1px;
      font-size: 0.68rem;
      line-height: 1.25;
      color: var(--muted);
    }
    .ts-chart-axis .ts-tick {
      min-width: 0;
      text-align: center;
    }
    .ts-chart-axis .ts-tick-group {
      flex: 6;
      white-space: normal;
      word-break: break-word;
      hyphens: manual;
      padding: 0 4px;
    }
    .line-chart { height: 120px; position: relative; border-left: 1px solid var(--border); border-bottom: 1px solid var(--border); }
    .line-chart svg { width: 100%; height: 100%; }
    footer { padding: 16px 24px; color: var(--muted); font-size: 0.75rem; border-top: 1px solid var(--border); }
    a { color: var(--accent); }
    .pill.err { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
    button.pill.err:hover {
      background: #fee2e2;
      border-color: #fca5a5;
      color: #7f1d1d;
    }
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
    a.session-id-link {
      color: var(--accent);
      text-decoration: underline;
      cursor: pointer;
      word-break: break-all;
    }
    a.session-id-link:hover { text-decoration: none; }
    .session-modal-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.45);
      z-index: 300;
      align-items: center;
      justify-content: center;
      padding: 12px;
    }
    .session-modal-backdrop.open { display: flex; }
    .pricing-modal-backdrop { z-index: 320; }
    .errors-modal-backdrop { z-index: 330; }
    .sessions-overview-backdrop { z-index: 327; }
    .session-modal.sessions-overview-panel {
      width: min(75vw, calc(100vw - 24px));
      max-width: min(75vw, calc(100vw - 24px));
    }
    .errors-pie-row {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      gap: 24px;
      justify-content: center;
      margin-top: 4px;
    }
    .errors-pie {
      width: 200px;
      height: 200px;
      border-radius: 50%;
      flex-shrink: 0;
      background: #e5e7eb;
      box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.06);
    }
    .errors-pie-legend {
      flex: 1;
      min-width: 220px;
      max-width: 440px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 0.82rem;
      line-height: 1.35;
    }
    .errors-pie-legend .err-leg-row {
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }
    .errors-top-callout {
      margin-top: 16px;
      padding: 12px 14px;
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 10px;
      color: #7f1d1d;
      font-size: 0.86rem;
      font-weight: 500;
      line-height: 1.45;
    }
    .errors-kv-row {
      display: grid;
      grid-template-columns: minmax(10rem, 11rem) 1fr;
      gap: 8px 12px;
      align-items: start;
      margin-bottom: 10px;
    }
    .errors-kv-row:last-child {
      margin-bottom: 0;
    }
    .errors-kv-key {
      font-weight: 700;
      color: #7f1d1d;
    }
    .errors-kv-val {
      font-weight: 600;
      word-break: break-word;
    }
    .errors-kv-log {
      margin: 0;
      font-family: ui-monospace, monospace;
      font-size: 0.78rem;
      font-weight: 500;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 220px;
      overflow-y: auto;
      background: rgba(255, 255, 255, 0.65);
      padding: 8px 10px;
      border-radius: 6px;
      border: 1px solid #fecaca;
      color: #450a0a;
    }
    .session-modal.errors-modal-panel {
      width: min(75vw, calc(100vw - 24px));
      max-width: min(75vw, calc(100vw - 24px));
    }
    .session-modal.pricing-modal-wide {
      width: min(75vw, calc(100vw - 24px));
      max-width: min(75vw, calc(100vw - 24px));
    }
    .pricing-catalog-table {
      width: 100%;
      font-size: 0.82rem;
      border-collapse: collapse;
    }
    .pricing-catalog-table th,
    .pricing-catalog-table td {
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
    }
    .pricing-catalog-table th {
      text-align: left;
      position: sticky;
      top: 0;
      background: #fff;
      z-index: 1;
      box-shadow: 0 1px 0 var(--border);
    }
    .pricing-catalog-table td.mono {
      font-family: ui-monospace, monospace;
      font-size: 0.78rem;
      word-break: break-all;
    }
    .pricing-catalog-table td.num {
      font-variant-numeric: tabular-nums;
      text-align: right;
      white-space: nowrap;
    }
    .pricing-table-wrap {
      max-height: min(52vh, 480px);
      overflow: auto;
      margin-top: 8px;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    .session-modal {
      width: min(75vw, calc(100vw - 24px));
      height: min(70vh, calc(100vh - 24px));
      max-width: min(75vw, calc(100vw - 24px));
      max-height: min(70vh, calc(100vh - 24px));
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 24px 60px rgba(0,0,0,.22);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid var(--border);
    }
    .session-modal-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
      gap: 12px;
    }
    .session-modal-head h2 {
      margin: 0;
      font-size: 0.95rem;
      font-weight: 600;
    }
    .session-modal-close {
      border: none;
      background: #f3f4f6;
      width: 32px;
      height: 32px;
      border-radius: 8px;
      font-size: 1.25rem;
      line-height: 1;
      cursor: pointer;
      color: var(--text);
      flex-shrink: 0;
    }
    .session-modal-close:hover { background: #e5e7eb; }
    .session-modal-body {
      padding: 12px 14px 14px;
      overflow-y: auto;
      flex: 1;
      min-height: 0;
      font-size: 0.86rem;
      line-height: 1.5;
    }
    .session-modal-body .mono { font-family: ui-monospace, monospace; font-size: 0.8rem; word-break: break-all; }
    .session-modal-body .times { margin: 8px 0; font-weight: 500; color: var(--text); }
    .session-modal-body .summary { margin: 0; color: #374151; }
    .session-detail-kv {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-bottom: 4px;
    }
    .session-detail-kv .session-kv-row {
      display: grid;
      grid-template-columns: minmax(11rem, 15rem) 1fr;
      gap: 8px 12px;
      align-items: start;
      font-size: 0.86rem;
      line-height: 1.45;
    }
    .session-detail-kv .session-kv-key {
      font-weight: 600;
      color: var(--text);
    }
    .session-detail-kv .session-kv-val {
      color: #374151;
      word-break: break-word;
    }
    .session-detail-kv .session-kv-val.mono {
      font-family: ui-monospace, monospace;
      font-size: 0.8rem;
    }
    .session-detail-kv pre.session-kv-val {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.84rem;
      color: #374151;
      line-height: 1.45;
    }
    .session-modal-body .errors-brief {
      margin: 12px 0 0;
      padding: 10px 12px;
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 8px;
      color: #7f1d1d;
      font-size: 0.84rem;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
      display: none;
    }
    .session-modal-body .errors-brief.visible { display: block; }
    .session-modal-body .foot { margin-top: 10px; font-size: 0.75rem; }
    @media (max-width: 640px) {
      .session-modal {
        width: min(92vw, calc(100vw - 24px));
        height: min(88vh, calc(100vh - 24px));
        max-width: min(92vw, calc(100vw - 24px));
        max-height: min(88vh, calc(100vh - 24px));
      }
      .session-modal.errors-modal-panel {
        width: min(75vw, calc(100vw - 24px));
        max-width: min(75vw, calc(100vw - 24px));
      }
      .session-modal.pricing-modal-wide {
        width: min(75vw, calc(100vw - 24px));
        max-width: min(75vw, calc(100vw - 24px));
      }
      .session-modal.sessions-overview-panel {
        width: min(75vw, calc(100vw - 24px));
        max-width: min(75vw, calc(100vw - 24px));
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>AdkTelemetry</h1>
    <div class="toolbar">
      <button type="button" class="pill" id="pill-sessions" aria-haspopup="dialog" aria-expanded="false" title="Open sessions overview for the selected time range">
        Sessions -
      </button>
      <button type="button" class="pill err" id="pill-errors" aria-haspopup="dialog" aria-expanded="false" title="Open error breakdown for the selected time range">
        Errors -
      </button>
      <button type="button" class="pill" id="pill-models" aria-haspopup="dialog" aria-expanded="false" title="Open Gemini FinOps rates (USD per 10K tokens)">
        Models in catalog -
      </button>
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
    <p class="muted" style="margin-top:0">AdkTelemetry - observability for Google ADK agents (events, tokens, FinOps). The dashboard refreshes when new telemetry is recorded (Server-Sent Events); when idle, only a lightweight keep-alive runs.</p>
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
        <div class="ts-chart-block">
          <div class="ts-chart" id="ts-chart"></div>
          <div class="ts-chart-axis" id="ts-chart-axis" aria-hidden="true"></div>
        </div>
        <p class="muted" style="margin-bottom:0">
          Event counts in 24 equal-width time buckets (selected dashboard range). Bar height is relative to the busiest bucket. Axis labels group 6 buckets each (local start–end).
        </p>
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
    These FinOps values ​​in AdkTelemetry were updated on 04/26 (month/year). Updated prices
    <a href="https://ai.google.dev/gemini-api/docs/pricing?hl=pt-br" target="_blank" rel="noopener">Gemini API pricing</a>.
  </footer>
  <div id="session-modal-backdrop" class="session-modal-backdrop" aria-hidden="true">
    <div class="session-modal" id="session-modal-panel" role="dialog" aria-modal="true" aria-labelledby="session-modal-title">
      <div class="session-modal-head">
        <h2 id="session-modal-title">Session detail</h2>
        <button type="button" class="session-modal-close" id="session-modal-close" aria-label="Close">×</button>
      </div>
      <div class="session-modal-body">
        <div id="session-modal-kv" class="session-detail-kv"></div>
        <div id="session-modal-errors" class="errors-brief" aria-live="polite"></div>
        <p id="session-modal-footnote" class="foot muted"></p>
      </div>
    </div>
  </div>
  <div id="pricing-modal-backdrop" class="session-modal-backdrop pricing-modal-backdrop" aria-hidden="true">
    <div class="session-modal pricing-modal-wide" id="pricing-modal-panel" role="dialog" aria-modal="true" aria-labelledby="pricing-modal-title">
      <div class="session-modal-head">
        <h2 id="pricing-modal-title">Gemini FinOps catalog</h2>
        <button type="button" class="session-modal-close" id="pricing-modal-close" aria-label="Close">×</button>
      </div>
      <div class="session-modal-body">
        <p class="muted" style="margin:0 0 4px" id="pricing-modal-unit"></p>
        <div class="pricing-table-wrap">
          <table class="pricing-catalog-table">
            <thead>
              <tr>
                <th>Model</th>
                <th style="text-align:right">Input USD / 10K</th>
                <th style="text-align:right">Output USD / 10K</th>
              </tr>
            </thead>
            <tbody id="pricing-modal-rows"></tbody>
          </table>
        </div>
        <p class="foot muted" id="pricing-modal-foot" style="margin-top:12px"></p>
      </div>
    </div>
  </div>
  <div id="errors-modal-backdrop" class="session-modal-backdrop errors-modal-backdrop" aria-hidden="true">
    <div class="session-modal errors-modal-panel" id="errors-modal-panel" role="dialog" aria-modal="true" aria-labelledby="errors-modal-title">
      <div class="session-modal-head">
        <h2 id="errors-modal-title">Error breakdown</h2>
        <button type="button" class="session-modal-close" id="errors-modal-close" aria-label="Close">×</button>
      </div>
      <div class="session-modal-body">
        <p class="muted" style="margin:0 0 8px" id="errors-modal-hint"></p>
        <div class="errors-pie-row">
          <div class="errors-pie" id="errors-pie-chart" aria-hidden="true"></div>
          <div class="errors-pie-legend" id="errors-pie-legend"></div>
        </div>
        <div id="errors-top-callout" class="errors-top-callout" style="display: none"></div>
      </div>
    </div>
  </div>
  <div id="sessions-overview-backdrop" class="session-modal-backdrop sessions-overview-backdrop" aria-hidden="true">
    <div class="session-modal sessions-overview-panel" id="sessions-overview-panel" role="dialog" aria-modal="true" aria-labelledby="sessions-overview-title">
      <div class="session-modal-head">
        <h2 id="sessions-overview-title">Sessions overview</h2>
        <button type="button" class="session-modal-close" id="sessions-overview-close" aria-label="Close">×</button>
      </div>
      <div class="session-modal-body">
        <p class="muted" style="margin:0 0 10px" id="sessions-overview-hint"></p>
        <div id="sessions-overview-kv" class="session-detail-kv"></div>
      </div>
    </div>
  </div>
  <script>
    // Caminho absoluto: com URL /adktelemetry (sem barra final), "./api/..." virava /api/... (404).
    const API = "/adktelemetry/api/v1/snapshot";
    const LIVE_STREAM = "/adktelemetry/api/v1/stream";
    const SESSION_DETAIL_API = "/adktelemetry/api/v1/session_detail";
    const PRICING_CATALOG_API = "/adktelemetry/api/v1/pricing_catalog";
    const ERROR_BREAKDOWN_API = "/adktelemetry/api/v1/error_breakdown";
    let liveEs = null;
    const colors = ["#22c55e","#3b82f6","#f97316","#ec4899","#a855f7","#14b8a6"];
    const errorPieColors = [
      "#b91c1c","#dc2626","#ef4444","#f43f5e","#e11d48","#ec4899","#db2777",
      "#d946ef","#c026d3","#a855f7","#9333ea","#7c3aed","#6d28d9","#5b21b6","#4c1d95",
    ];
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

    function appendBarRow(container, label, value, maxVal, variant) {
      const row = document.createElement("div");
      row.className = "bar-row";
      const pct = Math.round(100 * (Number(value) || 0) / maxVal);
      let fillClass = "bar-fill";
      if (variant === "error") fillClass += " bar-fill--err";
      else if (variant === "tok-in") fillClass += " bar-fill--tok-in";
      else if (variant === "tok-out") fillClass += " bar-fill--tok-out";
      row.innerHTML =
        '<div></div><div class="bar-track"><div class="' +
        fillClass +
        '" style="width:' +
        pct +
        '%"></div></div><div></div>';
      row.children[0].textContent = label;
      row.children[2].textContent = String(value);
      container.appendChild(row);
    }

    function appendSessionRow(tbody, s) {
      const tr = document.createElement("tr");
      if (Number(s.error_count) > 0) tr.className = "session-has-errors";
      const td0 = document.createElement("td");
      const link = document.createElement("a");
      link.href = "#";
      link.className = "session-id-link";
      link.textContent = s.session_id || "";
      link.dataset.sessionId = s.session_id || "";
      link.dataset.userId = s.user_id || "";
      td0.appendChild(link);
      tr.appendChild(td0);
      const cells = [
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
        const errTotal = (data.totals && data.totals.errors) || 0;
        const inTok = (data.totals && data.totals.total_input_tokens) || 0;
        const outTok = (data.totals && data.totals.total_output_tokens) || 0;
        const smaxEv = maxObj({ adk: events, errors: errTotal });
        const smaxTok = maxObj({ in: inTok, out: outTok });
        const bs = document.getElementById("bar-sources");
        bs.textContent = "";
        appendBarRow(bs, "adk", events, smaxEv, null);
        appendBarRow(bs, "errors", errTotal, smaxEv, "error");
        appendBarRow(bs, "in tok", inTok, smaxTok, "tok-in");
        appendBarRow(bs, "out tok", outTok, smaxTok, "tok-out");

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
        const axis = document.getElementById("ts-chart-axis");
        chart.textContent = "";
        if (axis) axis.textContent = "";
        const totalEv = events;
        const tl = data.activity_timeline;
        if (
          tl &&
          Array.isArray(tl.counts) &&
          tl.counts.length === n &&
          tl.since != null &&
          tl.until != null &&
          isFinite(Number(tl.since)) &&
          isFinite(Number(tl.until))
        ) {
          const since = Number(tl.since);
          const until = Number(tl.until);
          const span = until - since;
          const maxC = Math.max(0, ...tl.counts.map(function (x) { return Number(x) || 0; }));
          for (let i = 0; i < n; i++) {
            const c = Number(tl.counts[i]) || 0;
            const h = maxC > 0 ? Math.min(95, Math.max(4, (c / maxC) * 95)) : 4;
            const bucketStart = since + (span * i) / n;
            const bucketEnd = since + (span * (i + 1)) / n;
            const d = document.createElement("div");
            d.className = "ts-bar";
            d.style.height = h + "%";
            d.title =
              c +
              " event(s) · " +
              formatLocalTs(bucketStart) +
              " – " +
              formatLocalTs(bucketEnd);
            chart.appendChild(d);
          }
          if (axis) {
            const groupSize = 6;
            const numGroups = n / groupSize;
            for (let g = 0; g < numGroups; g++) {
              const i0 = g * groupSize;
              const rangeStart = since + (span * i0) / n;
              const rangeEnd = since + (span * (i0 + groupSize)) / n;
              const lab = document.createElement("span");
              lab.className = "ts-tick ts-tick-group";
              lab.textContent = formatTimelineRangeLabel(rangeStart, rangeEnd);
              lab.title =
                "Buckets " +
                (i0 + 1) +
                "–" +
                (i0 + groupSize) +
                ": " +
                formatLocalTs(rangeStart) +
                " – " +
                formatLocalTs(rangeEnd);
              axis.appendChild(lab);
            }
          }
        } else {
          for (let i = 0; i < n; i++) {
            const wave = 0.55 + 0.45 * Math.sin((i / n) * Math.PI * 2);
            const bucket = totalEv > 0 ? (totalEv / n) * (0.7 + 0.6 * wave) : 5 * wave;
            const h = Math.min(95, Math.max(6, (bucket / Math.max(totalEv / n, 1)) * 55));
            const d = document.createElement("div");
            d.className = "ts-bar";
            d.style.height = h + "%";
            d.title = "~" + Math.round(bucket) + " events (illustrative layout)";
            chart.appendChild(d);
          }
          if (axis) {
            const lab = document.createElement("span");
            lab.className = "ts-tick";
            lab.style.flex = "1";
            lab.textContent = "—";
            lab.title = "Time axis unavailable";
            axis.appendChild(lab);
          }
        }

        const svg = document.getElementById("line-svg");
        const ordered = sessions.slice().sort((a, b) => (b.last_timestamp || 0) - (a.last_timestamp || 0));
        const ptsIn = ordered.slice(0, 14).map((s, i) => ({ x: i, y: Number(s.total_input_tokens) || 0 }));
        const ptsOut = ordered.slice(0, 14).map((s, i) => ({ x: i, y: Number(s.total_output_tokens) || 0 }));
        const ymax = Math.max(1, ...ptsIn.map((p) => p.y), ...ptsOut.map((p) => p.y));
        function pathLine(pts) {
          if (!pts.length) return "";
          const n1 = Math.max(pts.length - 1, 1);
          const xLeft = 30;
          const xRight = 196;
          return pts
            .map((p, i) => {
              const x = xLeft + (i / n1) * (xRight - xLeft);
              const y = 88 - (p.y / ymax) * 72;
              return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
            })
            .join(" ");
        }
        const legend =
          '<g class="line-chart-legend" pointer-events="none">' +
          '<text x="4" y="12" font-size="8" fill="#3b82f6" paint-order="stroke" stroke="#ffffff" stroke-width="2.5">in</text>' +
          '<text x="4" y="22" font-size="8" fill="#22c55e" paint-order="stroke" stroke="#ffffff" stroke-width="2.5">out</text>' +
          "</g>";
        svg.innerHTML =
          '<path d="' +
          pathLine(ptsIn) +
          '" fill="none" stroke="#3b82f6" stroke-width="2" vector-effect="non-scaling-stroke"/>' +
          '<path d="' +
          pathLine(ptsOut) +
          '" fill="none" stroke="#22c55e" stroke-width="2" vector-effect="non-scaling-stroke"/>' +
          legend;
      } catch (e) {
        console.error("AdkTelemetry refresh:", e);
      }
    }
    function formatLocalTs(sec) {
      if (sec == null || sec === "" || !isFinite(Number(sec))) return "—";
      return new Date(Number(sec) * 1000).toLocaleString(undefined, {
        dateStyle: "short",
        timeStyle: "medium",
      });
    }

    function formatTimelineMdHm(d) {
      const mo = (d.getMonth() + 1).toString().padStart(2, "0");
      const da = d.getDate().toString().padStart(2, "0");
      const hh = d.getHours().toString().padStart(2, "0");
      const mm = d.getMinutes().toString().padStart(2, "0");
      return mo + "/" + da + " " + hh + ":" + mm;
    }

    function formatTimelineRangeLabel(startSec, endSec) {
      if (
        startSec == null ||
        endSec == null ||
        !isFinite(Number(startSec)) ||
        !isFinite(Number(endSec))
      ) {
        return "—";
      }
      const a = new Date(Number(startSec) * 1000);
      const b = new Date(Number(endSec) * 1000);
      return formatTimelineMdHm(a) + " - " + formatTimelineMdHm(b);
    }

    function closeSessionModal() {
      const backdrop = document.getElementById("session-modal-backdrop");
      if (backdrop) {
        backdrop.classList.remove("open");
        backdrop.setAttribute("aria-hidden", "true");
      }
    }

    function formatUsdPer10k(n) {
      const x = Number(n);
      if (!isFinite(x)) return "—";
      return x.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 8 });
    }

    function setPricingModalFooter(data) {
      const footEl = document.getElementById("pricing-modal-foot");
      if (!footEl) return;
      footEl.textContent = "";
      const updated = (data && data.catalog_updated) || "04/26";
      const url =
        (data && data.pricing_doc_url) ||
        "https://ai.google.dev/gemini-api/docs/pricing?hl=pt-br";
      footEl.appendChild(
        document.createTextNode(
          "These FinOps values in AdkTelemetry were last updated in " +
            updated +
            " (month/year). After that date, consult Google's official "
        )
      );
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "Gemini API pricing";
      footEl.appendChild(a);
      footEl.appendChild(
        document.createTextNode(
          ". Tiered or modality-specific pricing may differ from these reference rates."
        )
      );
    }

    function closePricingModal() {
      const backdrop = document.getElementById("pricing-modal-backdrop");
      const pill = document.getElementById("pill-models");
      if (backdrop) {
        backdrop.classList.remove("open");
        backdrop.setAttribute("aria-hidden", "true");
      }
      if (pill) pill.setAttribute("aria-expanded", "false");
    }

    function setErrorPieFromSlices(el, slices, total) {
      if (!el) return;
      if (!total || !slices.length) {
        el.style.background = "#e5e7eb";
        return;
      }
      let acc = 0;
      const parts = slices.map(function (s, i) {
        const pct = (100 * s.count) / total;
        const start = acc;
        acc += pct;
        const c = errorPieColors[i % errorPieColors.length];
        return c + " " + start + "% " + acc + "%";
      });
      el.style.background = "conic-gradient(" + parts.join(", ") + ")";
    }

    function closeErrorsModal() {
      const backdrop = document.getElementById("errors-modal-backdrop");
      const pill = document.getElementById("pill-errors");
      if (backdrop) {
        backdrop.classList.remove("open");
        backdrop.setAttribute("aria-hidden", "true");
      }
      if (pill) pill.setAttribute("aria-expanded", "false");
    }

    function closeSessionsOverviewModal() {
      const backdrop = document.getElementById("sessions-overview-backdrop");
      const pill = document.getElementById("pill-sessions");
      if (backdrop) {
        backdrop.classList.remove("open");
        backdrop.setAttribute("aria-hidden", "true");
      }
      if (pill) pill.setAttribute("aria-expanded", "false");
    }

    async function openSessionsOverviewModal() {
      const backdrop = document.getElementById("sessions-overview-backdrop");
      const kv = document.getElementById("sessions-overview-kv");
      const hint = document.getElementById("sessions-overview-hint");
      const pill = document.getElementById("pill-sessions");
      if (!backdrop || !kv || !hint) return;
      kv.textContent = "";
      hint.textContent = "Loading…";
      backdrop.classList.add("open");
      backdrop.setAttribute("aria-hidden", "false");
      if (pill) pill.setAttribute("aria-expanded", "true");
      try {
        const r = await fetch(API + "?" + snapshotQuery(), { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        hint.textContent =
          "Aggregates for the selected time range (dashboard clock, top-right). " +
          "Last interaction is the latest session activity timestamp in that window.";
        kv.textContent = "";
        const t = data.totals || {};
        const nSessions = t.sessions != null ? t.sessions : 0;
        const inTok = t.total_input_tokens != null ? t.total_input_tokens : 0;
        const outTok = t.total_output_tokens != null ? t.total_output_tokens : 0;
        const cost = t.total_cost_usd != null ? Number(t.total_cost_usd) : 0;
        const lastTs = t.last_interaction_ts;
        addSessionKvRow(kv, "Number of sessions:", String(nSessions), false, false);
        addSessionKvRow(kv, "Total input tokens:", String(inTok), false, false);
        addSessionKvRow(kv, "Total output tokens:", String(outTok), false, false);
        addSessionKvRow(kv, "Total cost (USD):", cost.toFixed(6), false, false);
        addSessionKvRow(
          kv,
          "Last interaction with the agent:",
          lastTs != null && lastTs !== "" && isFinite(Number(lastTs))
            ? formatLocalTs(lastTs)
            : "—",
          false,
          false
        );
      } catch (e) {
        hint.textContent = "";
        addSessionKvRow(
          kv,
          "Error:",
          "Could not load sessions overview. " + (e && e.message ? e.message : String(e)),
          true,
          false
        );
      }
    }

    function renderErrorsTopCallout(container, top) {
      container.textContent = "";
      container.style.display = "block";
      function addRow(keyText, valueText, usePre) {
        const row = document.createElement("div");
        row.className = "errors-kv-row";
        const k = document.createElement("span");
        k.className = "errors-kv-key";
        k.textContent = keyText;
        const v = document.createElement(usePre ? "pre" : "span");
        v.className = usePre ? "errors-kv-log" : "errors-kv-val";
        v.textContent = valueText;
        row.appendChild(k);
        row.appendChild(v);
        container.appendChild(row);
      }
      addRow("Most frequent:", top.label || "—", false);
      addRow("Event(s):", top.count != null ? String(top.count) : "—", false);
      addRow("% of total errors:", top.percent != null ? String(top.percent) + "%" : "—", false);
      addRow(
        "Full error log:",
        top.full_error_log != null && top.full_error_log !== "" ? top.full_error_log : "—",
        true
      );
    }

    async function openErrorsModal() {
      const backdrop = document.getElementById("errors-modal-backdrop");
      const pie = document.getElementById("errors-pie-chart");
      const leg = document.getElementById("errors-pie-legend");
      const hint = document.getElementById("errors-modal-hint");
      const topBox = document.getElementById("errors-top-callout");
      const pill = document.getElementById("pill-errors");
      if (!backdrop || !pie || !leg || !hint || !topBox) return;
      leg.textContent = "";
      topBox.style.display = "none";
      topBox.textContent = "";
      hint.textContent = "Loading…";
      pie.style.background = "#e5e7eb";
      backdrop.classList.add("open");
      backdrop.setAttribute("aria-hidden", "false");
      if (pill) pill.setAttribute("aria-expanded", "true");
      try {
        const r = await fetch(ERROR_BREAKDOWN_API + "?" + snapshotQuery(), { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        hint.textContent =
          "Total number of errors that occurred in the sessions: " +
          (data.total != null ? data.total : 0) +
          ".";
        if (!data.total) {
          setErrorPieFromSlices(pie, [], 0);
          const p = document.createElement("p");
          p.className = "muted";
          p.style.margin = "8px 0 0";
          p.textContent = "No errors in the selected time range.";
          leg.appendChild(p);
          return;
        }
        setErrorPieFromSlices(pie, data.slices || [], data.total);
        (data.slices || []).forEach(function (s, i) {
          const row = document.createElement("div");
          row.className = "err-leg-row";
          const sw = document.createElement("span");
          sw.style.cssText =
            "display:inline-block;width:12px;height:12px;border-radius:3px;margin-top:4px;flex-shrink:0;background:" +
            errorPieColors[i % errorPieColors.length];
          const txt = document.createElement("span");
          txt.textContent = s.label + " — " + s.percent + "% (" + s.count + ")";
          row.appendChild(sw);
          row.appendChild(txt);
          leg.appendChild(row);
        });
        const top = data.top;
        if (top) {
          renderErrorsTopCallout(topBox, top);
        }
      } catch (e) {
        hint.textContent =
          "Could not load error breakdown. " + (e && e.message ? e.message : String(e));
        setErrorPieFromSlices(pie, [], 0);
      }
    }

    async function openPricingModal() {
      const backdrop = document.getElementById("pricing-modal-backdrop");
      const tbody = document.getElementById("pricing-modal-rows");
      const unitEl = document.getElementById("pricing-modal-unit");
      const footEl = document.getElementById("pricing-modal-foot");
      const pill = document.getElementById("pill-models");
      if (!backdrop || !tbody) return;
      tbody.textContent = "";
      if (unitEl) unitEl.textContent = "Loading catalog…";
      if (footEl) footEl.textContent = "";
      backdrop.classList.add("open");
      backdrop.setAttribute("aria-hidden", "false");
      if (pill) pill.setAttribute("aria-expanded", "true");
      try {
        const r = await fetch(PRICING_CATALOG_API, { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        if (unitEl) unitEl.textContent = data.unit_label || "";
        setPricingModalFooter(data);
        const models = Array.isArray(data.models) ? data.models : [];
        models.forEach(function (m) {
          const tr = document.createElement("tr");
          const tdId = document.createElement("td");
          tdId.className = "mono";
          tdId.textContent = m.model_id || "";
          const tdIn = document.createElement("td");
          tdIn.className = "num";
          tdIn.textContent = formatUsdPer10k(m.input_usd_per_10k);
          const tdOut = document.createElement("td");
          tdOut.className = "num";
          tdOut.textContent = formatUsdPer10k(m.output_usd_per_10k);
          tr.appendChild(tdId);
          tr.appendChild(tdIn);
          tr.appendChild(tdOut);
          tbody.appendChild(tr);
        });
        if (!models.length && unitEl) unitEl.textContent = "No models in catalog.";
      } catch (e) {
        if (footEl) footEl.textContent = "";
        if (unitEl)
          unitEl.textContent =
            "Could not load catalog. " + (e && e.message ? e.message : String(e));
      }
    }

    function addSessionKvRow(container, keyText, valueText, usePre, monoVal) {
      const row = document.createElement("div");
      row.className = "session-kv-row";
      const k = document.createElement("span");
      k.className = "session-kv-key";
      k.textContent = keyText;
      let v;
      if (usePre) {
        v = document.createElement("pre");
        v.className = "session-kv-val";
      } else {
        v = document.createElement("span");
        v.className = "session-kv-val" + (monoVal ? " mono" : "");
      }
      v.textContent = valueText;
      row.appendChild(k);
      row.appendChild(v);
      container.appendChild(row);
    }

    function fillSessionModalKv(container, data, errorText) {
      container.textContent = "";
      if (errorText) {
        addSessionKvRow(container, "Error:", errorText, true, false);
        return;
      }
      addSessionKvRow(container, "Session ID:", data.session_id || "", false, true);
      addSessionKvRow(container, "User:", data.user_id || "", false, false);
      addSessionKvRow(
        container,
        "Conversation start (first buffered event):",
        formatLocalTs(data.started_ts),
        false,
        false
      );
      addSessionKvRow(
        container,
        "Last activity (last buffered event):",
        formatLocalTs(data.ended_ts),
        false,
        false
      );
      const st = data.stats;
      if (st && st.available) {
        addSessionKvRow(container, "Events in buffer:", String(st.buffer_events), false, false);
        addSessionKvRow(
          container,
          "Authors seen (order):",
          Array.isArray(st.authors_seen) ? st.authors_seen.join(", ") : "",
          false,
          false
        );
        addSessionKvRow(container, "Input tokens (buffer):", String(st.tokens_input), false, false);
        addSessionKvRow(container, "Output tokens (buffer):", String(st.tokens_output), false, false);
      } else {
        addSessionKvRow(container, "Buffer summary:", data.summary || "—", true, false);
      }
    }

    async function openSessionModal(sessionId, userId) {
      const backdrop = document.getElementById("session-modal-backdrop");
      const mkv = document.getElementById("session-modal-kv");
      const merrors = document.getElementById("session-modal-errors");
      const mfoot = document.getElementById("session-modal-footnote");
      if (!backdrop || !mkv) return;
      mkv.textContent = "";
      const load = document.createElement("p");
      load.className = "muted";
      load.style.margin = "0";
      load.textContent = "Loading…";
      mkv.appendChild(load);
      mfoot.textContent = "";
      if (merrors) {
        merrors.textContent = "";
        merrors.classList.remove("visible");
      }
      backdrop.classList.add("open");
      backdrop.setAttribute("aria-hidden", "false");
      try {
        const q = new URLSearchParams({ session_id: sessionId, user_id: userId });
        const r = await fetch(SESSION_DETAIL_API + "?" + q.toString(), { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        fillSessionModalKv(mkv, data, null);
        if (merrors) {
          if (data.errors_brief) {
            merrors.textContent = data.errors_brief;
            merrors.classList.add("visible");
          } else {
            merrors.textContent = "";
            merrors.classList.remove("visible");
          }
        }
        mfoot.textContent = data.disclaimer || "";
      } catch (e) {
        fillSessionModalKv(
          mkv,
          null,
          "Could not load session detail. " + (e && e.message ? e.message : String(e))
        );
      }
    }

    document.getElementById("session-modal-backdrop").addEventListener("click", closeSessionModal);
    document.getElementById("session-modal-panel").addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
    document.getElementById("session-modal-close").addEventListener("click", closeSessionModal);
    document.getElementById("pricing-modal-backdrop").addEventListener("click", closePricingModal);
    document.getElementById("pricing-modal-panel").addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
    document.getElementById("pricing-modal-close").addEventListener("click", closePricingModal);
    document.getElementById("errors-modal-backdrop").addEventListener("click", closeErrorsModal);
    document.getElementById("errors-modal-panel").addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
    document.getElementById("errors-modal-close").addEventListener("click", closeErrorsModal);
    document.getElementById("sessions-overview-backdrop").addEventListener("click", closeSessionsOverviewModal);
    document.getElementById("sessions-overview-panel").addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
    document.getElementById("sessions-overview-close").addEventListener("click", closeSessionsOverviewModal);
    document.getElementById("pill-models").addEventListener("click", function () {
      openPricingModal();
    });
    document.getElementById("pill-errors").addEventListener("click", function () {
      openErrorsModal();
    });
    document.getElementById("pill-sessions").addEventListener("click", function () {
      openSessionsOverviewModal();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key !== "Escape") return;
      const eb = document.getElementById("errors-modal-backdrop");
      if (eb && eb.classList.contains("open")) {
        closeErrorsModal();
        return;
      }
      const sob = document.getElementById("sessions-overview-backdrop");
      if (sob && sob.classList.contains("open")) {
        closeSessionsOverviewModal();
        return;
      }
      const pb = document.getElementById("pricing-modal-backdrop");
      if (pb && pb.classList.contains("open")) {
        closePricingModal();
        return;
      }
      closeSessionModal();
    });
    document.getElementById("session-rows").addEventListener("click", function (ev) {
      const a = ev.target.closest("a.session-id-link");
      if (!a) return;
      ev.preventDefault();
      openSessionModal(a.dataset.sessionId, a.dataset.userId);
    });

    function connectLiveStream() {
      if (liveEs) {
        liveEs.close();
        liveEs = null;
      }
      try {
        liveEs = new EventSource(LIVE_STREAM);
      } catch (e) {
        console.error("AdkTelemetry EventSource:", e);
        return;
      }
      liveEs.addEventListener("update", function () {
        refresh();
      });
      liveEs.onerror = function () {
        if (liveEs) {
          liveEs.close();
          liveEs = null;
        }
        setTimeout(connectLiveStream, 3000);
      };
    }

    updateRangeLabel();
    refresh();
    connectLiveStream();
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

    @app.get("/adktelemetry/api/v1/stream", include_in_schema=False)
    async def telemetry_live_stream() -> Any:
        from fastapi.responses import StreamingResponse

        from adktelemetry.live_notify import register_event_loop, subscribe, unsubscribe

        async def gen():
            loop = asyncio.get_running_loop()
            register_event_loop(loop)
            q = subscribe()
            try:
                yield b"event: ready\ndata: {}\n\n"
                while True:
                    try:
                        await asyncio.wait_for(q.get(), timeout=45.0)
                        yield b"event: update\ndata: {}\n\n"
                    except asyncio.TimeoutError:
                        yield b": keepalive\n\n"
            finally:
                unsubscribe(q)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/adktelemetry/api/v1/pricing_catalog", include_in_schema=False)
    async def pricing_catalog_api() -> Any:
        from fastapi.responses import JSONResponse

        from adktelemetry.config import get_config

        cfg = get_config()
        pricing_path = cfg.pricing_config_path if cfg else None
        payload = pricing_catalog(pricing_path)
        return JSONResponse(content=json.loads(json.dumps(payload, default=str)))

    @app.get("/adktelemetry/api/v1/error_breakdown", include_in_schema=False)
    async def error_breakdown_api(
        since: float | None = Query(None, description="Range start (Unix seconds)"),
        until: float | None = Query(None, description="Range end (Unix seconds)"),
    ) -> Any:
        from fastapi.responses import JSONResponse

        now = time.time()
        if since is None and until is None:
            payload = TelemetryStore.instance().error_breakdown(None, None)
            return JSONResponse(content=json.loads(json.dumps(payload, default=str)))

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
        payload = TelemetryStore.instance().error_breakdown(since_f, until_f)
        return JSONResponse(content=json.loads(json.dumps(payload, default=str)))

    @app.get("/adktelemetry/api/v1/session_detail", include_in_schema=False)
    async def session_detail(
        session_id: str = Query(..., min_length=1),
        user_id: str = Query(..., min_length=1),
    ) -> Any:
        from fastapi.responses import JSONResponse

        payload = TelemetryStore.instance().session_detail_payload(user_id, session_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found in telemetry store.",
            )
        return JSONResponse(content=json.loads(json.dumps(payload, default=str)))

    app.state.adktelemetry_registered = True

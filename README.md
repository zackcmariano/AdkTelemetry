# AdkTelemetry

![AdkTelemetry](https://raw.githubusercontent.com/zackcmariano/AdkTelemetry/refs/heads/master/assets/adk-telemetry-lib.png)

> **Observability & FinOps for Google ADK agents — in real time.**

AdkTelemetry is a **Python library for Google ADK** that captures **runner events**, **token usage**, **estimated USD cost**, and **error signals**, then exposes them through a **built-in dashboard** and a **JSON snapshot API**.

---

## What it does

- Wraps **`Runner.run_async`** so every yielded `Event` is summarized into an in-memory **`TelemetryStore`** (per `user_id` + `session_id`).
- Wraps the ADK dev server **`POST /run_sse`** stream so **synthetic `author: system` error lines** (exceptions caught inside the SSE generator) are also recorded. Those errors never pass through the runner hook alone, which is why this second path exists.
- Serves **`GET /adktelemetry`** (HTML UI) and **`GET /adktelemetry/api/v1/snapshot`** (JSON for the same data the UI uses).

Dashboard URL (with `adk web` on port 8080):

`http://localhost:8080/adktelemetry`

---

## Dashboard reference

The UI refreshes automatically every few seconds. All charts and tables respect the **selected time range** (see below), except when you open the snapshot without query parameters (full in-memory history).

### Header toolbar

| Control | Meaning |
|--------|---------|
| **Sessions** | Count of sessions that have activity in the current range (filtered mode) or total sessions in the store (unfiltered snapshot). |
| **Errors** | Sum of per-session error counts in the range. Aligns with error rows aggregated from events; the **Sessions Errors** table lists individual error records (capped). |
| **Pricing models** | Number of model IDs defined in `adktelemetry/gemini_pricing.yaml` (used for FinOps estimates). |
| **Time range** | Dropdown: **15 minutes**, **30 minutes**, **1 hour**, **12 hours**, or **custom start/end dates** (local timezone: start 00:00, end 23:59:59.999). Custom span cannot exceed **31 days**. Presets use a sliding window ending at “now” on each refresh. |

### Invocations by model

Donut chart plus legend: **distribution of model invocations** in the selected range. Counts come from per-event `model_version` (with FinOps resolution / fallback model when missing).

### ADK events (Runner)

Single bar: **total event count** in the range (same basis as the filtered `totals.events`).

### Estimated cost by session (USD)

- Lists sessions with **relative bar** and **cost** for the range (recomputed from events in the window).
- **Scroll area** shows roughly **seven** rows; additional sessions scroll inside the card.
- **Footer** (fixed below the scroll): **Total cost (all sessions)** = sum of `total_cost_usd` for **all** sessions that had activity in the range (not only the visible rows).

### Activity timeline (stacked)

**Synthetic buckets** derived from total event count in the selected range (visual scan, not wall-clock histogram). Subtitle states that it uses the selected time range.

### Token trend (in + out)

Line chart over the most recent sessions in the snapshot payload: **input tokens** vs **output tokens** (session-level totals for those rows).

### Sessions Errors

- Table: **Time**, **Session**, **Author**, **Code**, **Message**.
- Short description under the title explains that errors come from native `LlmResponse` fields and from **plain-text failures** (e.g. `Error: …`) on model/system content; the **Sessions** table **Errors** column uses the same per-session aggregation logic.
- **Scroll area** tuned for about **four** rows; wide messages may reduce how many full rows fit visually.
- The UI renders up to **40** error rows per refresh (the API may return more in the payload).

### Sessions

- Columns: **Session**, **User**, **Events**, **Errors**, **In tok**, **Out tok**, **Cost USD** (all recomputed for the selected range when filtering).
- Rows with **Errors > 0** use a light highlight.
- **Scroll area** tuned for about **ten** rows.
- The UI renders up to **50** session rows per refresh.

---

## REST API: snapshot

`GET /adktelemetry/api/v1/snapshot`

| Query | Description |
|-------|----------------|
| `since` | Optional. Start of range (**Unix seconds**). |
| `until` | Optional. End of range (**Unix seconds**). |

Rules:

- If **both** `since` and `until` are omitted, the response is the **full** in-memory aggregate (legacy behavior).
- If either is present, **`until`** defaults to the current server time and **`since`** defaults to 15 minutes before `until` when omitted.
- **`since` must be strictly before `until`**. Range length must be **≤ 31 days** or the server returns **400**.

The JSON body matches what the dashboard consumes, plus:

- `pricing_models`: size of the pricing catalog.
- `applied_range`: `{ "since": …, "until": … }` when filtering, or `null` for the full snapshot.

Filtered aggregates are computed by **replaying** stored per-session event records whose **`timestamp`** falls inside `[since, until]`. Events without a usable timestamp are skipped in filtered mode.

---

## How data is captured

1. **`ensure_runner_patch()`** (via `agentelemetry(...)`): patches **`google.adk.runners.Runner.run_async`**. Each yielded event is passed through **`event_to_record`** and **`TelemetryStore.record_event`**.
2. **`ensure_adk_web_server_patch()`** (via `services.py` under your agents dir): after the FastAPI app is built, registers dashboard routes and wraps **`POST /run_sse`** so SSE chunks that carry **system** `Error:` payloads are parsed and recorded. The wrapper updates **`route.dependant.call`** so FastAPI actually invokes the wrapper (replacing only `route.endpoint` is not enough).

---

## Configuration

```python
from adktelemetry import agentelemetry

agentelemetry(
    modelkey="YOUR_API_KEY",           # required
    adkmodel="gemini-2.5-flash",       # optional FinOps fallback when events lack model_version
    pricing_config_path=None,          # optional path to a custom gemini_pricing.yaml
)
```

Call `agentelemetry(...)` early (e.g. top of `app/agent.py`) so the runner patch is installed before runs.

For **`adk web`**, add **`services.py`** next to your app (same **`AGENTS_DIR`** root ADK loads). ADK imports it **before** `AdkWebServer.get_fast_api_app()`:

```python
from adktelemetry.patch_cli import ensure_adk_web_server_patch

ensure_adk_web_server_patch()
```

This registers `/adktelemetry` and the SSE error capture. See the **`agente-teste`** sample in this repository.

---

## FinOps

Default rates ship in **`adktelemetry/gemini_pricing.yaml`**. Update from [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) as needed. Costs are **estimates** based on token counts and that table.

---

## Limitations (in-memory store)

- **Per-session ring buffer** of recent raw event records (default 500). Very old events may be dropped; long custom ranges can be incomplete.
- **Global error list** is capped (200); the dashboard table shows up to **40** rows per refresh from the filtered/recent list.
- **Not durable**: process restart clears telemetry.

---

## Installation

```bash
pip install AdkTelemetry
```

Editable install from a checkout:

```bash
pip install -e .
```

---

## Quick start (minimal)

```python
from adktelemetry import agentelemetry

agentelemetry(
    adkmodel="gemini-2.5-flash",
    modelkey="YOUR_API_KEY",
)
```

Then run `adk web` with **`services.py`** calling `ensure_adk_web_server_patch()` and open `/adktelemetry`.

---

## License

MIT License © 2026

# AdkTelemetry

![AdkTelemetry](https://raw.githubusercontent.com/zackcmariano/AdkTelemetry/refs/heads/master/assets/adk-telemetry-lib.png)

> **Observability & FinOps for Google ADK agents — in real time.**

AdkTelemetry is a **Python library for Google ADK** that captures **runner events**, **token usage**, **estimated USD cost**, and **error signals**, then exposes them through a **built-in dashboard** and **JSON APIs**.

**Dashboard URL** (example with `adk web` on port 8080): `http://localhost:8080/adktelemetry`

---

## Installation

```bash
pip install AdkTelemetry
```

---

## Quick start (developer)

1. **Enable telemetry in your agent module** (call once at import time, before runs):

```python
from adktelemetry import agentelemetry

agentelemetry(
    modelkey="YOUR_GEMINI_API_KEY",  # required — use your app’s secret/config source
    adkmodel="gemini-2.5-flash",     # optional FinOps fallback when events lack model_version
)
```

2. **Register the dashboard with `adk web`** by adding a `services.py` next to your app (same **agents directory** root ADK loads). ADK imports it **before** the web server builds FastAPI:

```python
from adktelemetry.patch_cli import ensure_adk_web_server_patch

ensure_adk_web_server_patch()
```

3. Run `adk web`, open `/adktelemetry`, and use the time range control to match the window you care about.

**Configuration in code:** the library does not read environment variables by itself. You normally pass `modelkey` (and optionally `adkmodel`) from your own configuration — for example `os.environ["GEMINI_API_KEY"]`, a secrets manager, or Django settings.

---

## What you get (how to read the data)

| Surface | Purpose |
|--------|---------|
| **Dashboard** | Human-readable charts and tables; auto-refreshes about every **4 seconds**. |
| **`GET /adktelemetry/api/v1/snapshot`** | Same aggregates the UI uses; optional `since` / `until` (Unix seconds) for a time window. |
| **`GET /adktelemetry/api/v1/session_detail`** | Per-session brief from the in-memory buffer (`user_id`, `session_id` query params). |
| **`GET /adktelemetry/api/v1/pricing_catalog`** | Reference FinOps rates shown in the UI (USD per 10K tokens) plus a **catalog reference date** (month/year). |
| **`GET /adktelemetry/api/v1/error_breakdown`** | Error counts grouped by short label for the selected range (same query rules as snapshot). |

**Interpreting a snapshot (filtered mode):** `totals` rolls up only sessions that had at least one event in `[since, until]`. `sessions` and `model_distribution` are recomputed from stored events in that window. `applied_range` is `{ "since", "until" }` when filtering, or `null` for the full in-memory snapshot. `pricing_models` is the count of model IDs in the active FinOps catalog (informational; opens the catalog modal from the header).

**Events without a usable timestamp** are omitted when filtering by range, so very old or malformed records may not appear in windowed views.

---

## Dashboard guide (metrics & usability)

The layout is a single page: **header** (summary pills + time range), then a **grid** of cards, then **Sessions Errors** and **Sessions** tables. All numeric cards respect the **selected time range** except when you load the snapshot API with **no** `since`/`until` (full store).

### Time range (header, right)

| Control | Behavior |
|--------|----------|
| **15 / 30 minutes, 1 hour, 12 hours** | Sliding window ending at “now” on each refresh. |
| **Custom** | Start and end **dates** in the **local** timezone (start 00:00, end 23:59:59.999). Maximum span **31 days**. |

Changing the range updates the snapshot query, recomputes aggregates, and keeps drill-down modals aligned with the same window.

### Header pills (clickable)

| Pill | Shows | Click opens |
|------|--------|-------------|
| **Sessions** | Count of sessions with activity in the current range (or all sessions in unfiltered snapshot mode). | **Sessions overview** modal: total sessions, input/output tokens, total estimated USD, **last interaction** timestamp (latest session activity in the window). |
| **Errors** | Sum of per-session error counts in the range. | **Error breakdown** modal: pie chart by **short error label**, legend with % and counts, and a **top category** callout with a representative message when available. |
| **Pricing models** | Number of models in the FinOps catalog used for estimates. | **Gemini FinOps catalog** modal: table of **input/output USD per 10,000 tokens** per model, unit disclaimer, link to official Google pricing, and the **catalog reference month/year** (see FinOps below). |

### Invocations by model

- **Donut + legend** — share of **invocation counts** by resolved model key in the range.
- Counts come from each event’s `model_version`, with FinOps resolution and **fallback** to `adkmodel` when the event has no model.
- Legend lists up to **8** rows; the distribution object in JSON may contain more keys.

### ADK events (Runner)

Four **horizontal bars** (not a single combined scale):

1. **adk** — total **runner event** count in the range (`totals.events`).
2. **errors** — total error count (`totals.errors`), same basis as the Errors pill.
3. **in tok** / **out tok** — **prompt** and **candidates** token totals (`totals.total_input_tokens`, `totals.total_output_tokens`).

Bar length is **normalized within two groups**: events vs errors share one max; input vs output tokens share another. Use this card to compare **volume of ADK traffic**, **error load**, and **token volume** side by side.

### Estimated cost by session (USD)

- One row per session in the snapshot list: **truncated session id**, **relative bar** (max = largest session cost in the list), **cost** to six decimals.
- **Scroll** shows roughly **seven** rows; more sessions scroll inside the card.
- **Footer** — **Total cost (all sessions)** = sum of `total_cost_usd` for **every** session in the current range’s payload (not only visible rows). This matches FinOps recomputation from events in the window.

### Activity timeline (stacked)

- **24 equal-width time buckets** over the **selected dashboard range** (when filtering) or over min–max of buffered event timestamps (unfiltered full snapshot).
- Each bar’s **height** is relative to the **busiest bucket** (tooltip: event count + local time span for that bucket).
- **Axis labels** group **6 buckets** each (local start–end text).
- If timeline metadata is missing, the UI falls back to a **placeholder** layout (illustrative heights); with valid `activity_timeline.since` / `until` / `counts`, the chart is **wall-clock faithful** for the range.

### Token trend (in + out)

- Uses up to the **14 most recent sessions** in the snapshot (by `last_timestamp`), **not** chronological chat order.
- **Blue** = input tokens, **green** = output tokens per session.
- Lines are drawn with horizontal inset so paths do not run over the **in** / **out** legend text.

### Sessions Errors

- Columns: **Time**, **Session**, **Author**, **Code**, **Message**.
- Rows combine native **`LlmResponse`** error fields and **plain-text** failures (e.g. `Error: …`) on model/system content — same signals that increment the **Errors** column in **Sessions**.
- Up to **40** rows per refresh in the UI; the API may return more in `recent_errors` (still subject to the global in-memory cap — see limitations).

### Sessions

- Columns: **Session** (link), **User**, **Events**, **Errors**, **In tok**, **Out tok**, **Cost USD** — all **recomputed for the selected range** when filtering.
- Rows with **Errors > 0** are highlighted.
- Up to **50** session rows per refresh.
- **Click the session id** to open **Session detail** (modal): session/user ids, first/last buffered event times, buffer stats (event count, authors order, token totals from buffer), optional **errors brief**, and a short disclaimer that the brief is **deterministic** from the ring buffer (no LLM), and old events may have rotated out.

---

## REST API summary

### `GET /adktelemetry/api/v1/snapshot`

| Query | Description |
|-------|-------------|
| `since` | Optional. Range start (**Unix seconds**). |
| `until` | Optional. Range end (**Unix seconds**). |

- If **both** are omitted → full in-memory aggregate; `applied_range` is `null`.
- If either is set → **`until`** defaults to now, **`since`** defaults to **15 minutes** before `until` if omitted.
- **`since` < `until`** required; range length **≤ 31 days** or **400**.

### `GET /adktelemetry/api/v1/session_detail`

| Query | Description |
|-------|-------------|
| `session_id` | Required. |
| `user_id` | Required. |

Returns **404** if the session is unknown to the store.

### `GET /adktelemetry/api/v1/pricing_catalog`

Returns `models` (rows with `model_id`, `input_usd_per_10k`, `output_usd_per_10k`), `unit_label`, `catalog_updated` (MM/YY reference), and `pricing_doc_url`. Use this if you need the same reference the UI shows.

### `GET /adktelemetry/api/v1/error_breakdown`

Same `since` / `until` rules as snapshot. Body includes `total`, `slices` (`label`, `count`, `percent`), and optional `top` with a longer message sample for the dominant label.

---

## FinOps (estimates)

- Session and total **USD** values are **estimates** from **token counts** and the library’s **shipped FinOps catalog** (list-style rates). They are **not** a substitute for your Google Cloud / Gemini **billing** exports.
- **Tiered pricing, modalities, or discounts** may differ; the UI and catalog modal note that official pricing may vary.
- The **catalog reference date** appears as **month/year** (e.g. in the page footer, the FinOps catalog modal, and the `catalog_updated` field from **`/adktelemetry/api/v1/pricing_catalog`**). **Always check that date** when comparing estimates to real invoices — the catalog is refreshed on a schedule by **support / operations**, not by each application team.
- For the latest public list prices, use the linked **[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)** documentation.

---

## Limitations (in-memory store)

- **Per-session ring buffer** of recent raw events (default **500**). Long custom ranges can be incomplete if events aged out.
- **Global error list** is capped (**200**); the dashboard shows up to **40** error rows per refresh from the filtered/recent list.
- **Not durable**: process restart clears telemetry.

---

## License

MIT License © 2026

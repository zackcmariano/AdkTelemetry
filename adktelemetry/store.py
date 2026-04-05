"""In-memory telemetry store (per-session events, aggregates for dashboard)."""

from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from adktelemetry.finops import estimate_interaction_cost_usd, usage_metadata_to_counts
from adktelemetry.live_notify import notify_telemetry_changed, reset_for_tests as _reset_live_notify


def _now() -> float:
    return time.time()


@dataclass
class SessionRollup:
    user_id: str
    session_id: str
    event_count: int = 0
    error_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    last_timestamp: float = field(default_factory=_now)
    models: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "event_count": self.event_count,
            "error_count": self.error_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 8),
            "last_timestamp": self.last_timestamp,
            "models": dict(self.models),
        }


class TelemetryStore:
    _instance: TelemetryStore | None = None
    _lock = threading.RLock()

    def __init__(self, *, max_events_per_session: int = 500) -> None:
        self.max_events_per_session = max_events_per_session
        self._sessions: dict[str, SessionRollup] = {}
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._global_models: dict[str, int] = defaultdict(int)
        self._global_errors: list[dict[str, Any]] = []
        self._max_global_errors = 200

    @classmethod
    def instance(cls) -> TelemetryStore:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        _reset_live_notify()
        with cls._lock:
            cls._instance = cls()

    def record_event(
        self,
        *,
        user_id: str,
        session_id: str,
        record: dict[str, Any],
        default_model: str | None,
        pricing_config_path: str | None,
    ) -> None:
        key = f"{user_id}:{session_id}"
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = SessionRollup(user_id=user_id, session_id=session_id)
            roll = self._sessions[key]
            roll.event_count += 1
            roll.last_timestamp = _now()

            if _record_indicates_error(record):
                roll.error_count += 1
                if len(self._global_errors) < self._max_global_errors:
                    self._global_errors.append(
                        {
                            "ts": record.get("timestamp"),
                            "session_key": key,
                            "user_id": user_id,
                            "session_id": session_id,
                            "event_id": record.get("id"),
                            "invocation_id": record.get("invocation_id"),
                            "author": record.get("author"),
                            "error_code": record.get("error_code"),
                            "error_message": (record.get("error_message") or "")[:800],
                        }
                    )

            usage = record.get("usage") or {}
            pt = int(usage.get("prompt_token_count") or 0)
            ct = int(usage.get("candidates_token_count") or 0)
            roll.total_input_tokens += pt
            roll.total_output_tokens += ct

            model_for_cost = record.get("model_version") or default_model
            cost, resolved = estimate_interaction_cost_usd(
                model_id=model_for_cost,
                prompt_tokens=pt,
                output_tokens=ct,
                config_path=pricing_config_path,
            )
            roll.total_cost_usd += cost
            mkey = resolved or _normalize_model_label(model_for_cost)
            if mkey:
                roll.models[mkey] += 1
                self._global_models[mkey] += 1

            evs = self._events[key]
            evs.append(record)
            if len(evs) > self.max_events_per_session:
                del evs[: len(evs) - self.max_events_per_session]

        notify_telemetry_changed()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            sessions = [s.to_dict() for s in self._sessions.values()]
            sessions.sort(key=lambda x: x["last_timestamp"], reverse=True)
            err_total = sum(s.error_count for s in self._sessions.values())
            tok_in = sum(s.total_input_tokens for s in self._sessions.values())
            tok_out = sum(s.total_output_tokens for s in self._sessions.values())
            cost_sum = sum(float(s.total_cost_usd) for s in self._sessions.values())
            if self._sessions:
                last_ix = max(float(s.last_timestamp) for s in self._sessions.values())
            else:
                last_ix = None
            activity_timeline = _activity_timeline_from_events(
                self._events, range_since=None, range_until=None, n=24
            )
            return {
                "sessions": sessions[:100],
                "model_distribution": dict(self._global_models),
                "recent_errors": list(reversed(self._global_errors[-50:])),
                "activity_timeline": activity_timeline,
                "totals": {
                    "sessions": len(self._sessions),
                    "events": sum(s.event_count for s in self._sessions.values()),
                    "errors": err_total,
                    "total_input_tokens": tok_in,
                    "total_output_tokens": tok_out,
                    "total_cost_usd": round(cost_sum, 8),
                    "last_interaction_ts": last_ix,
                },
            }

    def error_breakdown(
        self, since: float | None, until: float | None
    ) -> dict[str, Any]:
        """
        Aggregate in-memory global error rows by short label for dashboard charts.
        If since and until are both None, uses the full buffered error list.
        """
        with self._lock:
            errs = list(self._global_errors)
        windowed: list[dict[str, Any]] = []
        if since is None and until is None:
            windowed = errs
        else:
            since_f = float(since)
            until_f = float(until)
            for e in errs:
                ts = e.get("ts")
                if ts is None:
                    continue
                try:
                    t = float(ts)
                except (TypeError, ValueError):
                    continue
                if since_f <= t <= until_f:
                    windowed.append(e)

        counts: dict[str, int] = defaultdict(int)
        for e in windowed:
            label = short_error_label_for_dashboard(e)
            counts[label] += 1

        total = sum(counts.values())
        if total == 0:
            return {"total": 0, "slices": [], "top": None}

        sorted_items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        slices: list[dict[str, Any]] = []
        for label, cnt in sorted_items:
            slices.append(
                {
                    "label": label,
                    "count": cnt,
                    "percent": round(100.0 * cnt / total, 1),
                }
            )
        top = slices[0]
        top_label = top["label"]
        top_entries = [
            e for e in windowed if short_error_label_for_dashboard(e) == top_label
        ]
        best_msg = ""
        for e in top_entries:
            msg = (e.get("error_message") or "").strip()
            if len(msg) > len(best_msg):
                best_msg = msg
        if not best_msg and top_entries:
            code = (top_entries[0].get("error_code") or "").strip()
            best_msg = (
                f"(No message text in telemetry; error_code={code!r})"
                if code
                else "No error message captured for this error class."
            )
        elif not best_msg:
            best_msg = "No error message captured for this error class."

        return {
            "total": total,
            "slices": slices,
            "top": {
                "label": top["label"],
                "count": top["count"],
                "percent": top["percent"],
                "full_error_log": best_msg,
            },
        }

    def session_detail_payload(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        """Compile a factual session brief from the in-memory event ring buffer (no LLM)."""
        key = f"{user_id}:{session_id}"
        with self._lock:
            if key not in self._events and key not in self._sessions:
                return None
            records = [dict(r) for r in self._events.get(key, [])]
            roll = self._sessions.get(key)

        summary = compile_session_summary_from_records(records)
        errors_brief = build_errors_brief(records)
        ts_vals = [_event_ts(r) for r in records]
        ts_vals = [t for t in ts_vals if t is not None]
        if ts_vals:
            start_ts = min(ts_vals)
            end_ts = max(ts_vals)
        elif roll is not None:
            t = float(roll.last_timestamp)
            start_ts = end_ts = t
        else:
            start_ts = None
            end_ts = None

        stats: dict[str, Any] | None = None
        sorted_recs = _sorted_ts_records(records)
        if sorted_recs is not None:
            authors_order: list[str] = []
            seen_a: set[str] = set()
            for r in sorted_recs:
                a = (r.get("author") or "").strip() or "unknown"
                if a not in seen_a:
                    seen_a.add(a)
                    authors_order.append(a)
            tot_in = sum(
                int((r.get("usage") or {}).get("prompt_token_count") or 0) for r in sorted_recs
            )
            tot_out = sum(
                int((r.get("usage") or {}).get("candidates_token_count") or 0)
                for r in sorted_recs
            )
            stats = {
                "available": True,
                "buffer_events": len(sorted_recs),
                "authors_seen": authors_order,
                "tokens_input": tot_in,
                "tokens_output": tot_out,
            }

        return {
            "session_id": session_id,
            "user_id": user_id,
            "summary": summary,
            "stats": stats,
            "errors_brief": errors_brief,
            "started_ts": start_ts,
            "ended_ts": end_ts,
            "buffer_event_count": len(records),
            "disclaimer": (
                "This brief is compiled deterministically from AdkTelemetry's in-memory event buffer "
                "for this session (no LLM). It reflects only what was captured; older events may have "
                "been rotated out of the buffer."
            ),
        }

    def snapshot_filtered(
        self,
        since: float,
        until: float,
        *,
        default_model: str | None,
        pricing_config_path: str | None,
    ) -> dict[str, Any]:
        """Recompute dashboard aggregates from stored per-session events in [since, until]."""
        with self._lock:
            since_f = float(since)
            until_f = float(until)
            sessions_raw: list[dict[str, Any]] = []
            model_distribution: dict[str, int] = defaultdict(int)

            for key, evs in self._events.items():
                filtered = _events_in_window(evs, since_f, until_f)
                if not filtered:
                    continue
                try:
                    user_id, session_id = key.split(":", 1)
                except ValueError:
                    continue
                roll = _rollup_records(
                    filtered,
                    user_id=user_id,
                    session_id=session_id,
                    default_model=default_model,
                    pricing_config_path=pricing_config_path,
                )
                sessions_raw.append(roll)
                for mk, mv in roll["models"].items():
                    model_distribution[mk] += int(mv)

            sessions_raw.sort(key=lambda x: x["last_timestamp"], reverse=True)
            sessions_out = sessions_raw[:100]

            err_list: list[dict[str, Any]] = []
            for e in self._global_errors:
                ts = e.get("ts")
                if ts is None:
                    continue
                try:
                    t = float(ts)
                except (TypeError, ValueError):
                    continue
                if since_f <= t <= until_f:
                    err_list.append(e)
            recent_errors = list(reversed(err_list[-50:]))

            err_total = sum(int(s["error_count"]) for s in sessions_raw)
            ev_total = sum(int(s["event_count"]) for s in sessions_raw)
            tok_in = sum(int(s["total_input_tokens"]) for s in sessions_raw)
            tok_out = sum(int(s["total_output_tokens"]) for s in sessions_raw)
            if sessions_raw:
                cost_sum = sum(float(s["total_cost_usd"]) for s in sessions_raw)
                last_ix = max(float(s["last_timestamp"]) for s in sessions_raw)
            else:
                cost_sum = 0.0
                last_ix = None

            activity_timeline = _activity_timeline_from_events(
                self._events,
                range_since=since_f,
                range_until=until_f,
                n=24,
            )

            return {
                "sessions": sessions_out,
                "model_distribution": dict(model_distribution),
                "recent_errors": recent_errors,
                "activity_timeline": activity_timeline,
                "totals": {
                    "sessions": len(sessions_raw),
                    "events": ev_total,
                    "errors": err_total,
                    "total_input_tokens": tok_in,
                    "total_output_tokens": tok_out,
                    "total_cost_usd": round(cost_sum, 8),
                    "last_interaction_ts": last_ix,
                },
            }


def _event_ts(rec: dict[str, Any]) -> float | None:
    ts = rec.get("timestamp")
    if ts is None:
        return None
    try:
        return float(ts)
    except (TypeError, ValueError):
        return None


def _events_in_window(
    evs: list[dict[str, Any]], since: float, until: float
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in evs:
        t = _event_ts(e)
        if t is None:
            continue
        if since <= t <= until:
            out.append(e)
    return out


def _activity_timeline_from_events(
    events_map: dict[str, list[dict[str, Any]]],
    *,
    range_since: float | None,
    range_until: float | None,
    n: int = 24,
) -> dict[str, Any]:
    """
    Histogram of event counts into n equal-width time buckets.
    If range_since/range_until are set, bucket edges match that window (dashboard range).
    If both are None, edges are min..max timestamp over all buffered events.
    """
    counts = [0] * n
    if range_since is not None and range_until is not None:
        since_f = float(range_since)
        until_f = float(range_until)
    else:
        all_ts: list[float] = []
        for evs in events_map.values():
            for e in evs:
                t = _event_ts(e)
                if t is not None:
                    all_ts.append(t)
        if not all_ts:
            return {"since": None, "until": None, "bucket_count": n, "counts": counts}
        since_f = min(all_ts)
        until_f = max(all_ts)

    span = until_f - since_f
    if span <= 0:
        span = 1.0
        mid = since_f
        since_f = mid - 0.5
        until_f = mid + 0.5

    rs = float(range_since) if range_since is not None else None
    ru = float(range_until) if range_until is not None else None

    for evs in events_map.values():
        for e in evs:
            t = _event_ts(e)
            if t is None:
                continue
            if rs is not None and ru is not None:
                if not (rs <= t <= ru):
                    continue
            elif not (since_f <= t <= until_f):
                continue
            idx = int((t - since_f) / span * n)
            if idx >= n:
                idx = n - 1
            elif idx < 0:
                idx = 0
            counts[idx] += 1

    return {
        "since": since_f,
        "until": until_f,
        "bucket_count": n,
        "counts": counts,
    }


def _rollup_records(
    records: list[dict[str, Any]],
    *,
    user_id: str,
    session_id: str,
    default_model: str | None,
    pricing_config_path: str | None,
) -> dict[str, Any]:
    models: dict[str, int] = defaultdict(int)
    event_count = len(records)
    error_count = 0
    total_input = 0
    total_output = 0
    total_cost = 0.0
    last_ts = 0.0

    for r in records:
        if _record_indicates_error(r):
            error_count += 1
        ts = _event_ts(r)
        if ts is not None:
            last_ts = max(last_ts, ts)

        usage = r.get("usage") or {}
        pt = int(usage.get("prompt_token_count") or 0)
        ct = int(usage.get("candidates_token_count") or 0)
        total_input += pt
        total_output += ct

        model_for_cost = r.get("model_version") or default_model
        cost, resolved = estimate_interaction_cost_usd(
            model_id=model_for_cost,
            prompt_tokens=pt,
            output_tokens=ct,
            config_path=pricing_config_path,
        )
        total_cost += cost
        mkey = resolved or _normalize_model_label(model_for_cost)
        if mkey:
            models[mkey] += 1

    return {
        "user_id": user_id,
        "session_id": session_id,
        "event_count": event_count,
        "error_count": error_count,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cost_usd": round(total_cost, 8),
        "last_timestamp": last_ts if last_ts > 0 else _now(),
        "models": dict(models),
    }


_MAX_COMBINED_TEXT = 12000

# finish_reason / API placeholders that must not count as user-visible failures
_BENIGN_ERROR_CODES = frozenset(
    {
        "",
        "NONE",
        "NULL",
        "STOP",
        "FINISH_REASON_STOP",
        "FINISHREASON.STOP",
        "UNKNOWN",
    }
)


def _record_indicates_error(rec: dict[str, Any]) -> bool:
    """True when the event should increment session error_count and Sessions Errors list."""
    if rec.get("error_inferred_from_content"):
        return bool((rec.get("error_message") or "").strip() or _non_benign_code(rec.get("error_code")))
    msg = (rec.get("error_message") or "").strip()
    if msg:
        return True
    return _non_benign_code(rec.get("error_code"))


def _non_benign_code(code: Any) -> bool:
    if code is None:
        return False
    c = str(code).strip().upper()
    if not c:
        return False
    if c in _BENIGN_ERROR_CODES:
        return False
    if c.endswith(".STOP") or c.endswith("_STOP"):
        return False
    return True


_ERR_STATUS_IN_TEXT_RE = re.compile(
    r"Error:\s*(\d{3})\s+([A-Za-z][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_ERR_LEADING_HTTP_RE = re.compile(
    r"^\s*(\d{3})\s+([A-Za-z][A-Za-z0-9_]*)\b",
)


def short_error_label_for_dashboard(entry: dict[str, Any]) -> str:
    """
    Short label for error breakdown UI, e.g. 'Error: 404 NOT_FOUND', 'Error: 503 UNAVAILABLE'.
    """
    msg = (entry.get("error_message") or "").strip()
    msg_one_line = " ".join(msg.split())
    m = _ERR_STATUS_IN_TEXT_RE.search(msg_one_line)
    if m:
        return f"Error: {m.group(1)} {m.group(2).upper()}"
    m2 = _ERR_LEADING_HTTP_RE.match(msg_one_line)
    if m2:
        return f"Error: {m2.group(1)} {m2.group(2).upper()}"
    code = (entry.get("error_code") or "").strip()
    if code and _non_benign_code(code):
        return f"Error: {code.upper()}"
    if msg_one_line:
        snippet = msg_one_line.split(".")[0].strip()
        if len(snippet) > 56:
            snippet = snippet[:53] + "…"
        if snippet.lower().startswith("error:"):
            return snippet if len(snippet) <= 72 else snippet[:69] + "…"
        combined = f"Error: {snippet}"
        return combined if len(combined) <= 72 else combined[:69] + "…"
    return "Error: unknown"


def _snippet_from_record(rec: dict[str, Any], *, max_len: int = 220) -> str:
    s = (rec.get("content_text_sample") or "").strip()
    if not s:
        tp = rec.get("text_preview")
        if isinstance(tp, list) and tp:
            s = " ".join(str(x) for x in tp[:3] if x)
    s = s.replace("\n", " ").strip()
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _sorted_ts_records(records: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Events that have a usable timestamp, oldest first."""
    with_ts: list[tuple[float, dict[str, Any]]] = []
    for r in records:
        t = _event_ts(r)
        if t is not None:
            with_ts.append((t, r))
    if not with_ts:
        return None
    with_ts.sort(key=lambda x: x[0])
    return [r for _, r in with_ts]


def build_errors_brief(records: list[dict[str, Any]], *, max_msg: int = 200, max_items: int = 3) -> str | None:
    """Short multi-line summary of error events (truncated); None if none."""
    sorted_recs = _sorted_ts_records(records)
    if not sorted_recs:
        return None
    err_recs = [r for r in sorted_recs if _record_indicates_error(r)]
    if not err_recs:
        return None
    lines: list[str] = [
        f"This session has {len(err_recs)} error-class event(s) in the telemetry buffer.",
    ]
    for i, r in enumerate(err_recs[:max_items], 1):
        code = ((r.get("error_code") or "").strip() or "unknown")
        msg = ((r.get("error_message") or "").strip().replace("\n", " "))
        if not msg:
            msg = _snippet_from_record(r, max_len=max_msg)
        if len(msg) > max_msg:
            msg = msg[: max_msg - 1] + "…"
        lines.append(f"{i}. [{code}] {msg}" if msg else f"{i}. [{code}]")
    if len(err_recs) > max_items:
        lines.append(f"… and {len(err_recs) - max_items} more (not shown).")
    return "\n".join(lines)


def compile_session_summary_from_records(records: list[dict[str, Any]]) -> str:
    """
    Build a short English brief from stored telemetry rows only (no generative model).
    """
    if not records:
        return (
            "No event rows are present in the telemetry ring buffer for this session. "
            "Either nothing was captured yet, or older rows were rotated out."
        )

    sorted_recs = _sorted_ts_records(records)
    if not sorted_recs:
        return (
            "Buffered events have no usable timestamps, so the conversation order cannot be "
            "reconstructed from telemetry alone."
        )

    authors_order: list[str] = []
    seen_a: set[str] = set()
    for r in sorted_recs:
        a = (r.get("author") or "").strip() or "unknown"
        if a not in seen_a:
            seen_a.add(a)
            authors_order.append(a)

    tot_in = sum(int((r.get("usage") or {}).get("prompt_token_count") or 0) for r in sorted_recs)
    tot_out = sum(int((r.get("usage") or {}).get("candidates_token_count") or 0) for r in sorted_recs)

    parts: list[str] = [
        f"{len(sorted_recs)} event(s) in buffer; authors seen in order: {', '.join(authors_order)}.",
        f"Token subtotals from buffered rows: {tot_in} input / {tot_out} output.",
    ]

    return " ".join(parts)


def _flatten_jsonish_strings(obj: Any, *, limit: int = 8000) -> str:
    """Collect string leaves from JSON-like trees (model_dump) for error scanning."""
    parts: list[str] = []
    n = 0

    def walk(x: Any) -> None:
        nonlocal n
        if n >= limit:
            return
        if isinstance(x, str) and x.strip():
            take = x[: min(len(x), limit - n)]
            parts.append(take)
            n += len(take)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return "\n".join(parts)[:limit]


def _strings_from_part(part: Any) -> list[str]:
    out: list[str] = []
    t = getattr(part, "text", None)
    if t:
        out.append(str(t))
    fr = getattr(part, "function_response", None)
    if fr is not None:
        resp = getattr(fr, "response", None)
        if resp is not None:
            try:
                out.append(json.dumps(resp, default=str))
            except TypeError:
                out.append(str(resp))
    cer = getattr(part, "code_execution_result", None)
    if cer is not None:
        co = getattr(cer, "output", None)
        if co:
            out.append(str(co))
    return out


def infer_content_runtime_error(text: str) -> tuple[str | None, str | None]:
    """
    Detect API/runtime failures delivered as plain text in model/system content
    (e.g. 'Error: 404 NOT_FOUND. {...}') where LlmResponse.error_* may be empty.
    """
    if not text or not str(text).strip():
        return None, None
    s = str(text).strip()
    low = s.lower()

    if low.startswith("error:"):
        m = re.match(r"Error:\s*(\d+)\s+([A-Za-z0-9_]+)", s)
        code = m.group(2).upper() if m and m.group(2) else None
        if not code and m and m.group(1):
            code = f"HTTP_{m.group(1)}"
        if not code:
            code = "RUNTIME_ERROR"
        return code, s[:4000]

    if re.search(r"\b404\b", s) and ("not_found" in low or "not found" in low):
        return "NOT_FOUND", s[:4000]
    if "permission_denied" in low or "permission denied" in low:
        return "PERMISSION_DENIED", s[:4000]
    if "resource_exhausted" in low or "resource exhausted" in low or "quota" in low:
        return "RESOURCE_EXHAUSTED", s[:4000]
    if "invalid_argument" in low or "invalid argument" in low:
        return "INVALID_ARGUMENT", s[:4000]
    if "unavailable" in low and ("503" in s or "unavailable" in low):
        return "UNAVAILABLE", s[:4000]

    return None, None


def _normalize_model_label(name: str | None) -> str | None:
    if not name:
        return None
    s = name.strip().lower()
    if s.startswith("models/"):
        s = s[7:]
    return s


def event_to_record(event: Any) -> dict[str, Any]:
    """Serialize ADK Event / LlmResponse fields for storage and API."""
    usage = getattr(event, "usage_metadata", None)
    pt, ct = usage_metadata_to_counts(usage)
    raw_code = getattr(event, "error_code", None)
    raw_msg = getattr(event, "error_message", None)
    rec: dict[str, Any] = {
        "id": getattr(event, "id", None),
        "timestamp": getattr(event, "timestamp", None),
        "author": getattr(event, "author", None),
        "invocation_id": getattr(event, "invocation_id", None),
        "branch": getattr(event, "branch", None),
        "error_code": str(raw_code) if raw_code is not None else None,
        "error_message": str(raw_msg) if raw_msg is not None else None,
        "model_version": getattr(event, "model_version", None),
        "partial": getattr(event, "partial", None),
        "finish_reason": str(getattr(event, "finish_reason", None) or "") or None,
        "usage": {
            "prompt_token_count": pt,
            "candidates_token_count": ct,
            "total_token_count": getattr(usage, "total_token_count", None) if usage else None,
        },
    }
    combined_chunks: list[str] = []
    title = getattr(event, "title", None)
    if title and str(title).strip():
        combined_chunks.append(str(title).strip())

    part_texts: list[str] = []
    content = getattr(event, "content", None)
    if content and getattr(content, "parts", None):
        for part in content.parts:
            for chunk in _strings_from_part(part):
                part_texts.append(chunk)
                combined_chunks.append(chunk)

    combined = "\n".join(combined_chunks)[:_MAX_COMBINED_TEXT]
    rec["text_preview"] = [t[:200] for t in part_texts[:3]]
    if combined:
        rec["content_text_sample"] = combined[:2000]

    scan = combined
    model_dump = getattr(event, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json", exclude_none=True)
            extra = _flatten_jsonish_strings(dumped, limit=8000)
            if extra.strip():
                scan = (combined + "\n" + extra if combined.strip() else extra)[:_MAX_COMBINED_TEXT]
        except Exception:
            pass

    if not rec.get("error_code") and not rec.get("error_message"):
        ic, im = infer_content_runtime_error(scan)
        if ic or im:
            rec["error_code"] = ic
            rec["error_message"] = im
            rec["error_inferred_from_content"] = True
    else:
        ic, im = infer_content_runtime_error(scan)
        if (ic or im) and not (rec.get("error_message") or "").strip():
            rec["error_code"] = ic or rec.get("error_code")
            rec["error_message"] = im
            rec["error_inferred_from_content"] = True

    return rec

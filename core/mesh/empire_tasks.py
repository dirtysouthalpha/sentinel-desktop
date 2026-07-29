"""Empire task handlers for the fleet mesh.

Maps empire-specific task types (yt-stats, alpaca-pnl, buffer-metrics,
empire-score, narrative) to real data sources. Each handler fetches
live metrics and returns structured results that downstream tasks
(empire-score aggregation, narrative generation) consume.

The handlers are intentionally stateless — credentials and endpoints
come from environment or params, so the same code runs on any mesh node.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Default endpoints — override via params or env vars for testability.
DEFAULT_YT_ANALYTICS_URL = os.environ.get("YT_ANALYTICS_URL", "")
DEFAULT_ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
DEFAULT_ALPACA_KEY_ID = os.environ.get("ALPACA_KEY_ID", "")
DEFAULT_ALPACA_SECRET = os.environ.get("ALPACA_SECRET", "")
DEFAULT_BUFFER_ACCESS_TOKEN = os.environ.get("BUFFER_ACCESS_TOKEN", "")


async def handle_yt_stats(task: dict[str, Any]) -> dict[str, Any]:
    """Fetch YouTube Analytics metrics for empire channels.

    Params:
        channel_id: YouTube channel ID (default: env EMPIRE_YT_CHANNEL_ID)
        metrics: list of metrics to fetch (default: ["views","subscribers","watch_time"])
        days: number of days to look back (default: 7)

    Returns dict with requested metrics.
    """
    params = task.get("params", {})
    channel_id = params.get("channel_id", os.environ.get("EMPIRE_YT_CHANNEL_ID", ""))
    metrics = params.get("metrics", ["views", "subscribers", "watch_time"])
    days = params.get("days", 7)

    # If a live endpoint is configured, hit it. Otherwise return structured stub.
    analytics_url = params.get("analytics_url", DEFAULT_YT_ANALYTICS_URL)
    if analytics_url and channel_id:
        try:
            import urllib.request
            url = f"{analytics_url}?channel={channel_id}&days={days}&metrics={','.join(metrics)}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                return {"channel_id": channel_id, "days": days, "source": "live", **data}
        except Exception as e:
            logger.warning("YT stats live fetch failed, falling back to stub: %s", e)

    # Structured stub for offline / test mode.
    stub = {"views": 0, "subscribers": 0, "watch_time_minutes": 0, "videos": []}
    return {
        "channel_id": channel_id or "stub",
        "days": days,
        "source": "stub",
        **{m: stub.get(m, 0) for m in metrics},
    }


async def handle_alpaca_pnl(task: dict[str, Any]) -> dict[str, Any]:
    """Fetch Alpaca paper-trading P&L and positions.

    Params:
        account_id: Alpaca account ID (optional)
        include_positions: whether to include open positions (default: True)

    Returns dict with equity, unrealized P&L, and positions.
    """
    params = task.get("params", {})
    include_positions = params.get("include_positions", True)

    base_url = params.get("base_url", DEFAULT_ALPACA_BASE_URL)
    key_id = params.get("key_id", DEFAULT_ALPACA_KEY_ID)
    secret = params.get("secret", DEFAULT_ALPACA_SECRET)

    if key_id and secret:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{base_url}/v2/account",
                headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                account = json.loads(resp.read().decode())

            result = {
                "account_id": account.get("id", ""),
                "equity": float(account.get("equity", 0)),
                "cash": float(account.get("cash", 0)),
                "unrealized_pl": float(account.get("unrealized_pl", 0)),
                "source": "live",
            }
            if include_positions:
                pos_req = urllib.request.Request(
                    f"{base_url}/v2/positions",
                    headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret},
                )
                with urllib.request.urlopen(pos_req, timeout=15) as pos_resp:
                    positions = json.loads(pos_resp.read().decode())
                result["positions"] = [
                    {"symbol": p.get("symbol"), "qty": p.get("qty"), "unrealized_pl": p.get("unrealized_pl")}
                    for p in positions
                ]
            return result
        except Exception as e:
            logger.warning("Alpaca live fetch failed, falling back to stub: %s", e)

    return {
        "account_id": "stub",
        "equity": 0.0,
        "cash": 0.0,
        "unrealized_pl": 0.0,
        "positions": [],
        "source": "stub",
    }


async def handle_buffer_metrics(task: dict[str, Any]) -> dict[str, Any]:
    """Fetch Buffer (social publishing) aggregate metrics.

    Params:
        organization_id: Buffer org ID (default: env BUFFER_ORG_ID)
        metrics: list of metrics (default: ["posts","impressions","engagement"])

    Returns dict with aggregate metrics.
    """
    params = task.get("params", {})
    org_id = params.get("organization_id", os.environ.get("BUFFER_ORG_ID", ""))
    metrics = params.get("metrics", ["posts", "impressions", "engagement"])

    token = params.get("access_token", DEFAULT_BUFFER_ACCESS_TOKEN)
    if token:
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.bufferapp.com/1/profiles.json",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                profiles = json.loads(resp.read().decode())
            return {
                "organization_id": org_id or "live",
                "profiles_count": len(profiles),
                "source": "live",
                "profiles": [{"id": p.get("id"), "service": p.get("service")} for p in profiles],
            }
        except Exception as e:
            logger.warning("Buffer live fetch failed, falling back to stub: %s", e)

    return {
        "organization_id": org_id or "stub",
        "posts": 0,
        "impressions": 0,
        "engagement": 0.0,
        "source": "stub",
    }


async def handle_empire_score(task: dict[str, Any]) -> dict[str, Any]:
    """Aggregate empire health score from upstream task results.

    Reads results from dependency tasks (yt-stats, alpaca-pnl, buffer-metrics)
    via the task's `dependency_results` param and computes a 0–100 score.

    Params:
        dependency_results: dict of {task_id: result_dict} from upstream tasks.
        weights: optional score component weights.

    Returns dict with total score and component breakdown.
    """
    params = task.get("params", {})
    dep_results = params.get("dependency_results", {})
    weights = params.get("weights", {
        "yt_growth": 0.25,
        "trading_pnl": 0.30,
        "social_engagement": 0.25,
        "content_output": 0.20,
    })

    # Compute component scores (0–100 each).
    yt = dep_results.get("yt-stats", {})
    alpaca = dep_results.get("alpaca-pnl", {})
    buffer = dep_results.get("buffer-metrics", {})

    yt_score = min(100, max(0, (yt.get("views", 0) / 1000) * 50 + (yt.get("subscribers", 0) / 100) * 50))
    trading_score = min(100, max(0, 50 + (alpaca.get("unrealized_pl", 0) / 1000) * 50))
    social_score = min(100, max(0, buffer.get("engagement", 0) * 10))
    content_score = min(100, max(0, (buffer.get("posts", 0) / 10) * 100))

    total = (
        yt_score * weights["yt_growth"]
        + trading_score * weights["trading_pnl"]
        + social_score * weights["social_engagement"]
        + content_score * weights["content_output"]
    )

    return {
        "total_score": round(total, 1),
        "components": {
            "yt_growth": round(yt_score, 1),
            "trading_pnl": round(trading_score, 1),
            "social_engagement": round(social_score, 1),
            "content_output": round(content_score, 1),
        },
        "source": "computed",
    }


async def handle_narrative(task: dict[str, Any]) -> dict[str, Any]:
    """Generate a natural-language narrative summary of empire metrics.

    Params:
        dependency_results: upstream task results (esp. empire-score).
        tone: "professional" | "casual" | "hype" (default: "professional").

    Returns dict with narrative text.
    """
    params = task.get("params", {})
    dep_results = params.get("dependency_results", {})
    tone = params.get("tone", "professional")

    score_data = dep_results.get("empire-score", {})
    total = score_data.get("total_score", 0)
    components = score_data.get("components", {})

    if tone == "hype":
        intro = f"Empire score: {total}/100 — we're crushing it!"
    elif tone == "casual":
        intro = f"Empire is sitting at {total}/100 right now."
    else:
        intro = f"Empire Health Score: {total}/100."

    detail_parts = []
    if components:
        for name, val in components.items():
            detail_parts.append(f"{name}: {val}")
    detail = " Component breakdown — " + "; ".join(detail_parts) + "." if detail_parts else ""

    return {
        "narrative": intro + detail,
        "tone": tone,
        "score": total,
        "source": "generated",
    }


# Registry mapping empire task types to their handlers.
EMPIRE_HANDLERS: dict[str, Any] = {
    "yt-stats": handle_yt_stats,
    "alpaca-pnl": handle_alpaca_pnl,
    "buffer-metrics": handle_buffer_metrics,
    "empire-score": handle_empire_score,
    "narrative": handle_narrative,
}

#!/usr/bin/env python3
"""
Brain Quality Maintenance Script
Prunes low-quality neurons, connects orphans, and enriches stale neurons
in the Neuralis brain.

Standalone CLI script — not part of core/.
Dry-run by default; pass --execute to actually mutate state.
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

logger = logging.getLogger("brain_quality_pass")

DEFAULT_BRAIN_URL = "http://localhost:8001"
DEFAULT_THRESHOLD = 0.3
DEFAULT_LIMIT = 100
STALE_DAYS = 30


def setup_logging(verbose: bool = False) -> None:
    """Configure console logging for the script."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.setLevel(level)


def health_check(url: str, timeout: int = 10) -> bool:
    """Verify the brain is reachable. Returns True if healthy."""
    try:
        r = requests.get(f"{url}/health", timeout=timeout)
        if r.status_code == 200:
            logger.info("Brain health check: OK")
            return True
        logger.error(
            "Brain health check failed: HTTP %d — %s", r.status_code, r.text
        )
        return False
    except requests.RequestException as e:
        logger.error("Brain unreachable at %s: %s", url, e)
        return False


def get_stats(url: str, timeout: int = 10) -> dict:
    """Fetch brain statistics."""
    try:
        r = requests.get(f"{url}/stats", timeout=timeout)
        if r.status_code == 200:
            return r.json()
        logger.error("Stats request failed: HTTP %d", r.status_code)
        return {}
    except requests.RequestException as e:
        logger.error("Failed to fetch stats: %s", e)
        return {}


def print_stats(stats: dict) -> None:
    """Pretty-print brain statistics."""
    if not stats:
        print("No stats available.")
        return
    print("\n=== Brain Statistics ===")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print()


def list_neurons(
    url: str,
    limit: int = 100,
    offset: int = 0,
    quality: Optional[float] = None,
    region: Optional[str] = None,
    timeout: int = 10,
) -> list:
    """List neurons with optional filters."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if quality is not None:
        params["quality"] = quality
    if region is not None:
        params["region"] = region
    try:
        r = requests.get(f"{url}/neurons", params=params, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            # API may return a list or a dict with a 'neurons' key
            if isinstance(data, list):
                return data
            return data.get("neurons", [])
        logger.error("List neurons failed: HTTP %d", r.status_code)
        return []
    except requests.RequestException as e:
        logger.error("Failed to list neurons: %s", e)
        return []


def search_neurons(url: str, query: str, limit: int = 10, timeout: int = 10) -> list:
    """Search neurons by semantic query."""
    try:
        r = requests.get(
            f"{url}/neurons/search", params={"q": query, "limit": limit}, timeout=timeout
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data
            return data.get("results", data.get("neurons", []))
        logger.error("Search failed: HTTP %d", r.status_code)
        return []
    except requests.RequestException as e:
        logger.error("Search request failed: %s", e)
        return []


def get_neuron(url: str, neuron_id: int, timeout: int = 10) -> Optional[dict]:
    """Fetch a single neuron by ID."""
    try:
        r = requests.get(f"{url}/neurons/{neuron_id}", timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return None
    except requests.RequestException:
        return None


def delete_neuron(url: str, neuron_id: int, timeout: int = 10) -> bool:
    """Delete a neuron by ID. Returns True on success."""
    try:
        r = requests.delete(f"{url}/neurons/{neuron_id}", timeout=timeout)
        return r.status_code in (200, 204)
    except requests.RequestException as e:
        logger.error("Delete neuron %d failed: %s", neuron_id, e)
        return False


def connect_neurons(
    url: str, source_id: int, target_id: int, timeout: int = 10
) -> bool:
    """Create a connection between two neurons."""
    try:
        r = requests.post(
            f"{url}/neurons/{source_id}/connect",
            json={"target_id": target_id},
            timeout=timeout,
        )
        return r.status_code == 200
    except requests.RequestException as e:
        logger.error(
            "Connect %d -> %d failed: %s", source_id, target_id, e
        )
        return False


def find_orphans(url: str, limit: int = 100, timeout: int = 10) -> list:
    """Find orphan neurons (no connections)."""
    neurons = list_neurons(url, limit=limit, timeout=timeout)
    orphans = []
    for n in neurons:
        connections = n.get("connections", [])
        # Also check connection_count field if present
        conn_count = n.get("connection_count", len(connections))
        if not connections and conn_count == 0:
            orphans.append(n)
    return orphans


def prune_low_quality(
    url: str,
    threshold: float = DEFAULT_THRESHOLD,
    limit: int = DEFAULT_LIMIT,
    execute: bool = False,
    timeout: int = 10,
) -> dict:
    """Find and optionally delete neurons below quality threshold.

    Returns a report dict with counts and details.
    """
    report = {"threshold": threshold, "found": 0, "deleted": 0, "failures": 0, "dry_run": not execute}
    # Fetch neurons with quality below threshold
    neurons = list_neurons(url, limit=limit, quality=threshold, timeout=timeout)
    # The API quality param may mean "max quality" or "min quality" depending
    # on implementation. Filter client-side to be safe.
    low_q = [n for n in neurons if n.get("quality", 1.0) < threshold]
    report["found"] = len(low_q)

    if not low_q:
        logger.info("No neurons below quality threshold %.2f", threshold)
        return report

    logger.info(
        "Found %d neurons below quality %.2f (limit=%d, execute=%s)",
        len(low_q), threshold, limit, execute,
    )

    for n in low_q[:limit]:
        nid = n.get("id")
        quality = n.get("quality", "?")
        topic = n.get("topic", "untitled")
        if execute:
            if delete_neuron(url, nid, timeout=timeout):
                report["deleted"] += 1
                logger.info("Deleted neuron %d (quality=%s, topic=%s)", nid, quality, topic)
            else:
                report["failures"] += 1
                logger.warning("Failed to delete neuron %d", nid)
        else:
            logger.info(
                "[DRY-RUN] Would delete neuron %d (quality=%s, topic=%s)",
                nid, quality, topic,
            )
    return report


def connect_orphans(
    url: str,
    limit: int = DEFAULT_LIMIT,
    execute: bool = False,
    timeout: int = 10,
) -> dict:
    """Find orphan neurons and connect them to the most similar neuron.

    Returns a report dict.
    """
    report = {"found": 0, "connected": 0, "failures": 0, "dry_run": not execute}
    orphans = find_orphans(url, limit=limit, timeout=timeout)
    report["found"] = len(orphans)

    if not orphans:
        logger.info("No orphan neurons found.")
        return report

    logger.info("Found %d orphan neurons (execute=%s)", len(orphans), execute)

    for orphan in orphans[:limit]:
        oid = orphan.get("id")
        topic = orphan.get("topic", "")
        content = orphan.get("content", "")
        search_query = topic or content[:100] or "general"
        candidates = search_neurons(url, query=search_query, limit=5, timeout=timeout)
        # Filter out self
        candidates = [c for c in candidates if c.get("id") != oid]
        if not candidates:
            logger.warning("No connection candidate for orphan %d", oid)
            report["failures"] += 1
            continue
        target = candidates[0]
        tid = target.get("id")
        if execute:
            if connect_neurons(url, oid, tid, timeout=timeout):
                report["connected"] += 1
                logger.info("Connected orphan %d -> %d", oid, tid)
            else:
                report["failures"] += 1
                logger.warning("Failed to connect orphan %d -> %d", oid, tid)
        else:
            logger.info("[DRY-RUN] Would connect orphan %d -> %d", oid, tid)
    return report


def enrich_stale(
    url: str,
    days: int = STALE_DAYS,
    limit: int = DEFAULT_LIMIT,
    timeout: int = 10,
) -> dict:
    """Find neurons not fired in N days and flag them (report only)."""
    report = {"stale_days": days, "found": 0, "flagged": 0}
    neurons = list_neurons(url, limit=limit, timeout=timeout)
    cutoff = datetime.now() - timedelta(days=days)
    stale = []
    for n in neurons:
        last_fired = n.get("last_fired") or n.get("last_fired_at") or n.get("updated_at")
        if not last_fired:
            # No fire timestamp — treat as stale
            stale.append(n)
            continue
        try:
            # Try common ISO formats
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    fired_at = datetime.strptime(str(last_fired)[:19], fmt)
                    break
                except ValueError:
                    continue
            else:
                fired_at = None
            if fired_at and fired_at < cutoff:
                stale.append(n)
        except (ValueError, TypeError):
            pass

    report["found"] = len(stale)
    report["flagged"] = len(stale)
    for n in stale:
        nid = n.get("id")
        topic = n.get("topic", "untitled")
        last_fired = n.get("last_fired", "never")
        logger.info(
            "STALE neuron %d (topic=%s, last_fired=%s) — flag for review",
            nid, topic, last_fired,
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Brain quality maintenance — prune, connect, enrich.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --stats                        # show brain stats\n"
            "  %(prog)s --prune                        # dry-run prune\n"
            "  %(prog)s --prune --execute              # actually delete\n"
            "  %(prog)s --auto                         # full dry-run pass\n"
            "  %(prog)s --auto --execute               # full execute pass\n"
        ),
    )
    parser.add_argument(
        "--url", default=DEFAULT_BRAIN_URL,
        help=f"Brain base URL (default: {DEFAULT_BRAIN_URL})",
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help=f"Quality threshold for pruning (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"Max neurons to process per operation (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Preview changes without modifying state (default)",
    )
    parser.add_argument(
        "--execute", action="store_true", default=False,
        help="Actually perform deletions/connections",
    )
    parser.add_argument(
        "--auto", action="store_true", default=False,
        help="Run full auto pass: prune + connect + enrich",
    )
    parser.add_argument("--stats", action="store_true", help="Show brain statistics")
    parser.add_argument("--prune", action="store_true", help="Prune low-quality neurons")
    parser.add_argument("--connect-orphans", action="store_true", help="Connect orphan neurons")
    parser.add_argument("--enrich", action="store_true", help="Flag stale neurons")
    parser.add_argument("--stale-days", type=int, default=STALE_DAYS, help=f"Stale threshold in days (default: {STALE_DAYS})")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return parser


def main(argv: Optional[list] = None) -> int:
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(verbose=args.verbose)

    # Health check first
    if not health_check(args.url):
        logger.error("Brain unreachable — aborting.")
        return 1

    # --execute overrides --dry-run
    execute = args.execute
    if execute:
        logger.warning("EXECUTE mode enabled — changes will be applied!")
    else:
        logger.info("Dry-run mode — no changes will be applied.")

    # If no action specified, default to stats
    any_action = args.auto or args.stats or args.prune or args.connect_orphans or args.enrich
    if not any_action:
        args.stats = True

    if args.stats:
        stats = get_stats(args.url)
        print_stats(stats)

    if args.auto or args.prune:
        logger.info("--- Prune low-quality neurons ---")
        report = prune_low_quality(
            url=args.url,
            threshold=args.threshold,
            limit=args.limit,
            execute=execute,
        )
        print(f"\nPrune report: {report}\n")

    if args.auto or args.connect_orphans:
        logger.info("--- Connect orphan neurons ---")
        report = connect_orphans(
            url=args.url,
            limit=args.limit,
            execute=execute,
        )
        print(f"\nConnect orphans report: {report}\n")

    if args.auto or args.enrich:
        logger.info("--- Enrich stale neurons ---")
        report = enrich_stale(
            url=args.url,
            days=args.stale_days,
            limit=args.limit,
        )
        print(f"\nEnrich stale report: {report}\n")

    logger.info("Brain quality pass complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

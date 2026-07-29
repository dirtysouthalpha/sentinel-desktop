"""
Sentinel Desktop v31.0.0 - Entry Point
AI-powered desktop automation assistant.

Usage:
    python main.py              # Launch GUI (v23 engine)
    python main.py --cli        # CLI mode
    python main.py --api        # Headless API server
    python main.py --legacy-gui # Legacy GUI (v6.x engine)
    python main.py --version
"""
import argparse
import sys
import uuid


def parse_args():
    """Parse command-line arguments. Exported for testing."""
    parser = argparse.ArgumentParser(description="Sentinel Desktop v31.0.0")
    parser.add_argument("--cli", "-c", nargs="?", const=True, default=False,
                        help="Run in CLI mode (optionally with command)")
    parser.add_argument("--api", action="store_true", help="Run headless API server")
    parser.add_argument("--host", default="0.0.0.0", help="API listen host")
    parser.add_argument("--port", type=int, default=8091, help="API listen port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no actions)")
    parser.add_argument("--autonomous", action="store_true", help="Autonomous mode")
    parser.add_argument("--legacy-gui", action="store_true",
                        help="Launch legacy v6.x GUI (deprecated)")
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("--mesh", action="store_true", help="Enable fleet mesh mode")
    parser.add_argument("--fleet", nargs="*", default=None,
                        metavar="COMMAND",
                        help="Fleet mesh CLI (status, nodes, plans, deploy, ...)")
    parser.add_argument("--node-id", type=str, default=None, help="Unique node ID for mesh mode")
    parser.add_argument("--node-priority", type=str, default="desktop",
                        choices=["cns", "prime", "desktop", "agent_zero"],
                        help="Node priority for leader election")
    args = parser.parse_args()
    if isinstance(args.cli, str):
        args.command = args.cli
        args.cli = True
    else:
        args.command = None
    return args


async def _run_mesh_node(node, _bus, _election, _orch):
    """Keep the mesh node alive with periodic heartbeats."""
    import asyncio
    while True:
        node.heartbeat()
        await asyncio.sleep(15)


def main():
    """Entry point for Sentinel Desktop."""
    args = parse_args()

    if args.version:
        from core import __version__
        print(f"Sentinel Desktop v{__version__}")
        return

    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    # Fleet CLI mode
    if args.fleet is not None:
        from core.mesh.cli import FleetCLI
        cli = FleetCLI()
        output = cli.execute(args.fleet)
        print(output)
        return

    # Fleet mesh mode
    if args.mesh:
        from core.mesh import EventBus, LeaderElection, MeshNode, NodeCapabilities, NodePriority, Orchestrator
        from core.mesh.cache import StateCache

        logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
        logger = logging.getLogger("mesh")

        priority_map = {
            "cns": NodePriority.CNS,
            "prime": NodePriority.PRIME,
            "desktop": NodePriority.DESKTOP,
            "agent_zero": NodePriority.AGENT_ZERO,
        }
        node_priority = priority_map[args.node_priority]
        node_id = args.node_id or f"node-{args.node_priority}-{uuid.uuid4().hex[:6]}"

        bus = EventBus()
        cache = StateCache(db_path=f"mesh_{node_id}.db")
        election = LeaderElection(lease_ttl=30)
        capabilities = NodeCapabilities(
            can_orchestrate=node_priority >= NodePriority.DESKTOP,
            can_execute_desktop=node_priority == NodePriority.DESKTOP,
            can_reason=True,
            can_remember=True,
        )
        node = MeshNode(node_id=node_id, name=f"Mesh-{args.node_priority}", priority=node_priority, capabilities=capabilities)
        node.heartbeat()
        orch = Orchestrator(event_bus=bus, cache=cache, leader_election=election, node_id=node_id)

        logger.info("Fleet mesh mode enabled (node_id=%s, priority=%s)", node_id, args.node_priority)
        logger.info("Node capabilities: orchestrate=%s, execute=%s, reason=%s",
                     capabilities.can_orchestrate, capabilities.can_execute_desktop, capabilities.can_reason)

        # Keep mesh alive
        try:
            import asyncio
            asyncio.run(_run_mesh_node(node, bus, election, orch))
        except KeyboardInterrupt:
            logger.info("Mesh node shutting down")
        return

    # API server mode
    if args.api:
        import uvicorn

        from api.server import InsecureBindError, SentinelServer, require_secure_bind
        from config import Config

        # Fail fast rather than publishing unauthenticated RCE to the network.
        try:
            require_secure_bind(args.host)
        except InsecureBindError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)

        config = Config()
        config.load()
        server = SentinelServer(config)
        app = server.create_app()
        uvicorn.run(app, host=args.host, port=args.port)
        return

    # Legacy GUI mode (v6.x — deprecated)
    if args.legacy_gui:
        import warnings
        warnings.warn(
            "Legacy GUI (v6.x) is deprecated. Use the default GUI mode instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from src.ui.app import main as legacy_gui_main
        legacy_gui_main()
        return

    # CLI mode
    if args.cli:
        from core.cli import cli_main
        cli_main()
        return

    # Default GUI mode (v23 engine)
    try:
        from gui.app import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"GUI dependencies missing: {e}")
        print("Install with: pip install customtkinter pyautogui psutil pystray")
        print("Falling back to legacy GUI...")
        try:
            from src.ui.app import main as legacy_gui_main
            legacy_gui_main()
        except ImportError as e2:
            print(f"Legacy GUI also failed: {e2}")
            sys.exit(1)


if __name__ == "__main__":
    main()

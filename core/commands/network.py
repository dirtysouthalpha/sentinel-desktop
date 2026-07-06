"""
Network Diagnostic Commands
Ping, IP config, connectivity checks, speedtest.
"""
import subprocess
import platform
from core.legacy_engine import CommandResult


class NetworkCommands:
    """Network diagnostic utilities."""

    def ping(self, host: str) -> CommandResult:
        count = "-n" if platform.system() == "Windows" else "-c"
        try:
            result = subprocess.run(
                ["ping", count, "4", host],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout.strip()
            return CommandResult(True, f"Ping {host}:\n{output}")
        except subprocess.TimeoutExpired:
            return CommandResult(False, f"Ping to {host} timed out")
        except Exception as e:
            return CommandResult(False, f"Ping failed: {e}")

    def ipconfig(self) -> CommandResult:
        is_win = platform.system() == "Windows"
        cmd = ["ipconfig", "/all"] if is_win else ["ifconfig"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout.strip()
            return CommandResult(True, f"Network Configuration:\n{output}")
        except Exception as e:
            return CommandResult(False, f"IP config failed: {e}")

    def diagnostics(self) -> CommandResult:
        """Full network diagnostic suite."""
        results = []
        is_win = platform.system() == "Windows"

        # 1. Check connectivity
        results.append("=== Connectivity Check ===")
        count = "-n" if is_win else "-c"
        try:
            r = subprocess.run(
                ["ping", count, "1", "8.8.8.8"],
                capture_output=True, text=True, timeout=5
            )
            if "ttl" in r.stdout.lower() or "time=" in r.stdout.lower():
                results.append("Internet: CONNECTED")
            else:
                results.append("Internet: DISCONNECTED")
        except Exception:
            results.append("Internet: UNKNOWN")

        # 2. DNS check
        results.append("\n=== DNS Resolution ===")
        try:
            r = subprocess.run(
                ["nslookup", "google.com"],
                capture_output=True, text=True, timeout=5
            )
            results.append(r.stdout.strip()[:500])
        except Exception as e:
            results.append(f"DNS check failed: {e}")

        # 3. Active connections
        results.append("\n=== Active Connections ===")
        try:
            cmd = ["netstat", "-an"] if is_win else ["ss", "-tlnp"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            lines = r.stdout.strip().split("\n")
            results.append("\n".join(lines[:20]))
        except Exception:
            results.append("Could not retrieve connections")

        # 4. Default route
        results.append("\n=== Default Gateway ===")
        try:
            if is_win:
                r = subprocess.run(["route", "print", "0.0.0.0"], capture_output=True, text=True, timeout=5)
            else:
                r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5)
            results.append(r.stdout.strip()[:500])
        except Exception:
            results.append("Could not retrieve gateway")

        return CommandResult(True, "\n".join(results))

    def speedtest(self) -> CommandResult:
        """Quick network speed test."""
        try:
            import speedtest
            st = speedtest.Speedtest()
            st.get_best_server()
            dl = st.download() / 1_000_000
            ul = st.upload() / 1_000_000
            ping = st.results.ping
            msg = (
                f"Speed Test Results:\n"
                f"  Download: {dl:.1f} Mbps\n"
                f"  Upload: {ul:.1f} Mbps\n"
                f"  Ping: {ping}ms"
            )
            return CommandResult(True, msg)
        except ImportError:
            return CommandResult(False, "speedtest-cli not installed. Run: pip install speedtest-cli")
        except Exception as e:
            return CommandResult(False, f"Speedtest failed: {e}")

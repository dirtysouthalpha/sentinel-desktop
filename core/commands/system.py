"""
System Diagnostic Commands
CPU, Memory, Disk, Process monitoring.
"""
import psutil
import platform
import os
import time
from core.legacy_engine import CommandResult


class SystemCommands:
    """System information and diagnostics."""

    def cpu_usage(self) -> CommandResult:
        cpu = psutil.cpu_percent(interval=1)
        cores = psutil.cpu_count()
        freq = psutil.cpu_freq()
        freq_str = f"{freq.current:.0f}MHz" if freq else "N/A"
        msg = f"CPU Usage: {cpu}%\nCores: {cores} ({os.cpu_count()} logical)\nFrequency: {freq_str}"
        return CommandResult(True, msg, {"cpu": cpu, "cores": cores})

    def memory_usage(self) -> CommandResult:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        used_gb = mem.used / (1024**3)
        total_gb = mem.total / (1024**3)
        msg = (
            f"Memory: {mem.percent}% used\n"
            f"  RAM: {used_gb:.1f}GB / {total_gb:.1f}GB\n"
            f"  Swap: {swap.percent}% ({swap.used/(1024**3):.1f}GB / {swap.total/(1024**3):.1f}GB)"
        )
        return CommandResult(True, msg, {"percent": mem.percent, "used_gb": used_gb})

    def disk_usage(self) -> CommandResult:
        results = []
        data = {}
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                results.append(
                    f"  {part.device} ({part.mountpoint}): {usage.percent}% - "
                    f"{usage.used/(1024**3):.0f}GB / {usage.total/(1024**3):.0f}GB"
                )
                data[part.mountpoint] = usage.percent
            except Exception:
                continue
        msg = "Disk Usage:\n" + "\n".join(results)
        return CommandResult(True, msg, data)

    def list_processes(self, limit: int = 15) -> CommandResult:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # Sort by CPU
        procs.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
        top = procs[:limit]
        lines = [f"  {p['pid']:>6} | {p['name']:<30} | CPU: {p.get('cpu_percent', 0):.1f}% | MEM: {p.get('memory_percent', 0):.1f}%" for p in top]
        msg = f"Top {limit} Processes:\n" + "\n".join(lines)
        return CommandResult(True, msg, {"count": len(procs), "top": top})

    def system_info(self) -> CommandResult:
        msg = (
            f"System Information:\n"
            f"  OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
            f"  Host: {platform.node()}\n"
            f"  Python: {platform.python_version()}\n"
            f"  CPU: {os.cpu_count()} cores\n"
            f"  RAM: {psutil.virtual_memory().total/(1024**3):.1f}GB\n"
            f"  Boot: {time.ctime(psutil.boot_time())}"
        )
        return CommandResult(True, msg)

    def battery_info(self) -> CommandResult:
        try:
            bat = psutil.sensors_battery()
            if bat:
                plug = "Plugged in" if bat.power_plugged else "Battery"
                msg = f"Battery: {bat.percent}% ({plug})"
                if not bat.power_plugged and bat.secsleft != psutil.POWER_TIME_UNLIMITED:
                    hours = bat.secsleft / 3600
                    msg += f" - ~{hours:.1f}h remaining"
                return CommandResult(True, msg)
            return CommandResult(False, "No battery detected (desktop system).")
        except Exception as e:
            return CommandResult(False, f"Battery check failed: {e}")

    def temperature(self) -> CommandResult:
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return CommandResult(False, "Temperature sensors not available.")
            lines = []
            for name, entries in temps.items():
                for entry in entries:
                    lines.append(f"  {name}/{entry.label or 'core'}: {entry.current}\u00b0C")
            return CommandResult(True, "Temperatures:\n" + "\n".join(lines))
        except Exception as e:
            return CommandResult(False, f"Temperature check failed: {e}")

    def uptime(self) -> CommandResult:
        boot = psutil.boot_time()
        uptime_secs = time.time() - boot
        hours = int(uptime_secs // 3600)
        mins = int((uptime_secs % 3600) // 60)
        msg = f"Uptime: {hours}h {mins}m\nBooted: {time.ctime(boot)}"
        return CommandResult(True, msg)

    def help(self) -> CommandResult:
        """Show available commands."""
        from core.commands.help_data import HELP_TEXT
        return CommandResult(True, HELP_TEXT)

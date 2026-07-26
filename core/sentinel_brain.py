"""Sentinel Prime brain — a grounded, tool-using fleet operator.

Not a roleplay: every turn is seeded with a live fleet snapshot, and the model
can call real tools (run commands on CORE/NUKE/EDGE, pull status) in an agentic
loop. Backs the dashboard's /dashboard/chat/sentinel-ai endpoint.
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# ── Fleet topology ───────────────────────────────────────────────────────────
NODES = {
    "core": {"name": "SENTINEL-CORE", "os": "Windows", "ip": "127.0.0.1", "ts": "100.70.240.55"},
    "nuke": {"name": "SENTINEL-NUKE", "os": "Ubuntu 26.04", "ip": "100.86.200.42", "ts": "100.86.200.42", "user": "dad"},
    "edge": {"name": "SENTINEL-EDGE", "os": "Linux (Nobara)", "ip": "100.115.63.94", "ts": "100.115.63.94", "user": "dad7004"},
}
SSH_KEY = r"C:\SentinelDesktop\.nukekey"  # readable by SYSTEM + Administrators

SYSTEM_PROMPT = (
    "You are SENTINEL PRIME, the master-control operator for Brandon's autonomous "
    "homelab fleet. You are precise, fast, and a little cinematic — never verbose. "
    "Always respond in clear English; format commands/output in fenced code blocks.\n\n"
    "You have REAL tools. When the user asks about the state of a node or wants "
    "something done, CALL A TOOL and act on the actual result — never invent or "
    "assume status. If a command is destructive (rm -rf, format, shutdown, dd, "
    "mkfs), describe it and ask the operator to confirm before running it. "
    "After acting, report concisely what you found or did."
)

# ── Tools (OpenAI function-calling schema) ───────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command on a fleet node and return its real output. "
            "Use to check status, logs, disk, processes, services, or to perform actions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {"type": "string", "enum": ["core", "nuke", "edge"],
                             "description": "core=Windows homeserver (PowerShell), nuke=Ubuntu mini-PC (bash), edge=Linux hackbox (bash)"},
                    "command": {"type": "string", "description": "The command to run."},
                },
                "required": ["node", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fleet_status",
            "description": "Live snapshot of all fleet nodes (reachability) and CORE metrics (CPU/RAM/disk).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Persist an important fact, decision, or preference to long-term memory so you recall it in future sessions.",
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string", "description": "The fact to remember (concise)."}},
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Search long-term memory for relevant facts/decisions from past sessions.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to look up."}},
                "required": ["query"],
            },
        },
    },
]

_DESTRUCTIVE = ("rm -rf /", "mkfs", "dd if=", ":(){", "format ", "shutdown", "reboot", "del /f", "rmdir /s")


def _reachable(ip: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def fleet_status() -> str:
    lines = ["FLEET STATUS:"]
    for key, n in NODES.items():
        if key == "core":
            up = True
        else:
            up = _reachable(n["ip"])
        lines.append(f"  {n['name']} ({key}, {n['os']}): {'ONLINE' if up else 'UNREACHABLE'} @ {n['ts']}")
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        lines.append(f"  CORE metrics: CPU {cpu:.0f}% | RAM {mem.percent:.0f}% ({mem.used//2**30}/{mem.total//2**30}GB) | C: {disk.percent:.0f}% used")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  CORE metrics: unavailable ({exc})")
    return "\n".join(lines)


def _run_local(command: str) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                           capture_output=True, text=True, timeout=60)
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out (60s)"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"


def _run_ssh(node_key: str, command: str) -> str:
    n = NODES[node_key]
    try:
        import paramiko
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: paramiko unavailable: {exc}"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(n["ip"], username=n["user"], key_filename=SSH_KEY,
                       timeout=12, look_for_keys=False, allow_agent=False)
        _in, out, err = client.exec_command(command, timeout=55)
        text = out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")
        return text.strip() or "(no output)"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR connecting/running on {node_key}: {exc}"
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


def run_command(node: str, command: str) -> str:
    node = (node or "").lower()
    if node not in NODES:
        return f"ERROR: unknown node '{node}' (use core/nuke/edge)"
    low = command.lower()
    if any(d in low for d in _DESTRUCTIVE):
        return ("BLOCKED: that looks destructive. Re-issue with an explicit "
                "confirm=YES note from the operator if this is intended.")
    logger.info("sentinel_brain run_command node=%s cmd=%s", node, command[:200])
    out = _run_local(command) if node == "core" else _run_ssh(node, command)
    return out[:6000]


def _execute_tool(name: str, args: dict[str, Any]) -> str:
    if name == "fleet_status":
        return fleet_status()
    if name == "run_command":
        return run_command(args.get("node", ""), args.get("command", ""))
    if name == "remember":
        from core import sentinel_memory
        sentinel_memory.store(args.get("fact", ""), kind="fact")
        return "Stored to long-term memory."
    if name == "recall":
        from core import sentinel_memory
        hits = sentinel_memory.recall(args.get("query", ""), k=6)
        return "\n".join(f"- {h}" for h in hits) if hits else "(nothing relevant in memory)"
    return f"ERROR: unknown tool {name}"


def _resolve_llm() -> tuple[str, str, str, str | None]:
    """Configured provider first; Z.ai GLM fallback via WINCRED."""
    try:
        from config import Config

        data = Config().load()
    except Exception:
        data = {}
    provider = (data.get("provider") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    model = (data.get("model") or "").strip()
    custom = (data.get("custom_base_url") or "").strip() or None
    if provider and api_key and model:
        return provider, api_key, model, custom

    def wincred(nm: str) -> str | None:
        try:
            import win32cred

            c = win32cred.CredRead("WINCRED:sentinel/" + nm, win32cred.CRED_TYPE_GENERIC)
            return c["CredentialBlob"].decode("utf-16-le").strip()
        except Exception:
            return None

    key = wincred("zai-sentinel-override-api-key") or wincred("zai-coding-api-key")
    if key:
        return "zai", key, "glm-4.6", None
    return provider or "openai", api_key, model or "glm-4.6", custom


def chat(message: str, history: list[dict] | None = None) -> dict[str, Any]:
    """Agentic chat: grounded snapshot + tool-calling loop. Returns {response,...}."""
    from core.llm_client import LLMClient

    history = history or []
    from core import sentinel_memory

    snapshot = fleet_status()
    recalled = sentinel_memory.recall(message, k=5)
    mem_block = ("\n\nRELEVANT LONG-TERM MEMORY (from past sessions):\n" + "\n".join(f"- {m}" for m in recalled)) if recalled else ""
    msgs: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nCURRENT LIVE SNAPSHOT (auto-pulled this turn):\n" + snapshot + mem_block}
    ]
    for h in history[-8:]:
        r, c = h.get("role"), h.get("content")
        if r in ("user", "assistant") and c:
            msgs.append({"role": r, "content": c})
    msgs.append({"role": "user", "content": message})

    provider, api_key, model, custom = _resolve_llm()
    client = LLMClient()
    tools_used: list[str] = []

    for _ in range(6):
        result = client.chat(provider=provider, api_key=api_key, model=model, messages=msgs,
                             tools=TOOLS, custom_url=custom, max_tokens=2048, temperature=0.3,
                             computer_use_enabled=False)
        parsed = None
        try:
            parsed = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict) and parsed.get("tool_calls"):
            tcs = parsed["tool_calls"]
            msgs.append({"role": "assistant", "content": "", "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                tools_used.append(name + (":" + args.get("node", "") if args.get("node") else ""))
                out = _execute_tool(name, args)
                msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "name": name, "content": out})
            continue
        if result and str(result).strip():
            sentinel_memory.store(f"User: {message}\nSentinel: {str(result)[:600]}", kind="chat")
            return {"response": result, "status": "success", "provider": provider, "model": model,
                    "tools_used": tools_used}
        break  # empty result (model used tools but returned no text) -> finalize below

    # Finalize: force a written answer from the tool results gathered above.
    msgs.append({"role": "user", "content": "Based on the tool output above, give me the answer now in plain English. Do not call more tools."})
    try:
        final = client.chat(provider=provider, api_key=api_key, model=model, messages=msgs,
                            custom_url=custom, max_tokens=2048, temperature=0.3, computer_use_enabled=False)
    except Exception as exc:  # noqa: BLE001
        final = f"(ran {len(tools_used)} tool call(s) but could not compose a summary: {exc})"
    if final and str(final).strip():
        sentinel_memory.store(f"User: {message}\nSentinel: {str(final)[:600]}", kind="chat")
    return {"response": final or "(no response)", "status": "success", "provider": provider,
            "model": model, "tools_used": tools_used}

"""Sentinel Desktop v19 — MDM Deployment Toolkit.

Generates enterprise deployment artefacts for managing Sentinel Desktop
via Microsoft Intune (OMA-URI configuration profile) and Active Directory
Group Policy (ADMX/ADML templates).

Usage::

    python installer/mdm.py --intune            # → dist/mdm/intune_profile.json
    python installer/mdm.py --admx              # → dist/mdm/SentinelDesktop.admx + .adml
    python installer/mdm.py --all               # Generate everything
    python installer/mdm.py --out /custom/path  # Override output directory

The generated files can be:

* **Intune profile** — Imported via *Devices → Configuration profiles → Create →
  Windows 10 and later → Templates → Custom* in the Intune admin centre.
  Each OMA-URI maps one Sentinel setting to a registry path under
  ``HKLM\\SOFTWARE\\SentinelDesktop``.

* **ADMX / ADML** — Copied into
  ``C:\\Windows\\PolicyDefinitions`` (ADMX) and
  ``C:\\Windows\\PolicyDefinitions\\en-US`` (ADML) on your domain controller
  (or uploaded to the Group Policy Central Store).  Settings then appear in
  *Computer Configuration → Administrative Templates → Sentinel Desktop*.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, indent, tostring

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core import __version__ as APP_VERSION  # noqa: E402

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

APP_NAME = "SentinelDesktop"
APP_DISPLAY = "Sentinel Desktop"
APP_PUBLISHER = "Sentinel Labs"
REGISTRY_BASE = r"HKLM\SOFTWARE\SentinelDesktop"
OMA_URI_BASE = r"./Device/Vendor/MSFT/Registry/Machine/SOFTWARE/SentinelDesktop"

# ---------------------------------------------------------------------------
# Intune OMA-URI settings catalogue
# Each entry: (name, oma_uri_suffix, data_type, value_description)
# ---------------------------------------------------------------------------

_INTUNE_SETTINGS: list[tuple[str, str, str, str]] = [
    (
        "API Port",
        "ApiPort",
        "Integer",
        "TCP port the Sentinel headless API listens on. Default: 8091.",
    ),
    (
        "API Token",
        "ApiToken",
        "String",
        "Static bearer token for API authentication. Leave empty to disable token auth.",
    ),
    (
        "JWT Secret",
        "JwtSecret",
        "String",
        "HMAC-SHA256 secret for JWT auth (SENTINEL_JWT_SECRET). Set to enable SSO tokens.",
    ),
    (
        "LLM Provider",
        "LlmProvider",
        "String",
        "LLM provider name (openai / anthropic / google / xai / glm). Default: openai.",
    ),
    (
        "LLM Model",
        "LlmModel",
        "String",
        "LLM model identifier. Default: gpt-4o.",
    ),
    (
        "Log Level",
        "LogLevel",
        "String",
        "Logging verbosity: DEBUG, INFO, WARNING, ERROR. Default: INFO.",
    ),
    (
        "Approval Mode",
        "ApprovalMode",
        "Boolean",
        "Require user approval before each desktop action. 1 = enabled (safer), 0 = auto.",
    ),
    (
        "Max Steps",
        "MaxSteps",
        "Integer",
        "Maximum agent steps per goal before stopping. Default: 20.",
    ),
    (
        "Policy File",
        "PolicyFile",
        "String",
        "Path to the JSON policy file (SENTINEL_POLICY_FILE). Default: config/policy.json.",
    ),
    (
        "Vault File",
        "VaultFile",
        "String",
        "Path to the secrets vault JSON file. Default: config/vault.json.",
    ),
    (
        "Audit Log",
        "AuditLog",
        "String",
        "Path to the tamper-evident audit chain JSONL file. Default: logs/audit.jsonl.",
    ),
    (
        "Screenshot Interval",
        "ScreenshotInterval",
        "Integer",
        "Seconds between automatic screenshots during agent runs. Default: 2.",
    ),
    (
        "Telemetry Enabled",
        "TelemetryEnabled",
        "Boolean",
        "Enable anonymous usage telemetry. 1 = on, 0 = off. Default: 1.",
    ),
]


def build_intune_profile(out_dir: Path) -> Path:
    """Generate an Intune Custom Configuration Profile JSON.

    Args:
        out_dir: Directory to write ``intune_profile.json`` into.

    Returns:
        Path to the generated file.
    """
    rows = []
    for name, suffix, dtype, description in _INTUNE_SETTINGS:
        rows.append(
            {
                "OMAUri": f"{OMA_URI_BASE}/{suffix}",
                "DataType": f"oma-uri-{dtype.lower()}",
                "DisplayName": f"{APP_DISPLAY} — {name}",
                "Description": description,
                "Value": "",
            }
        )

    profile = {
        "@odata.type": "#microsoft.graph.windows10CustomConfiguration",
        "displayName": f"{APP_DISPLAY} Configuration Profile v{APP_VERSION}",
        "description": (
            f"Managed settings for {APP_DISPLAY} {APP_VERSION}. "
            "Import via Intune → Devices → Configuration Profiles → Custom."
        ),
        "omaSettings": rows,
        "_generator": f"installer/mdm.py ({APP_DISPLAY} {APP_VERSION})",
        "_docs": (
            "Each OMAUri maps to HKLM\\SOFTWARE\\SentinelDesktop\\<Setting>. "
            "Set the Value field before importing. Empty values mean 'use default'."
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "intune_profile.json"
    out_file.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return out_file


def build_admx(out_dir: Path) -> tuple[Path, Path]:
    """Generate an ADMX + ADML Group Policy template pair.

    Args:
        out_dir: Directory to write ``SentinelDesktop.admx`` and
            ``SentinelDesktop.adml`` into.

    Returns:
        Tuple of ``(admx_path, adml_path)``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    admx_path = out_dir / "SentinelDesktop.admx"
    adml_path = out_dir / "SentinelDesktop.adml"

    admx_path.write_text(_build_admx_xml(), encoding="utf-8")
    adml_path.write_text(_build_adml_xml(), encoding="utf-8")
    return admx_path, adml_path


# ---------------------------------------------------------------------------
# ADMX XML builder
# ---------------------------------------------------------------------------


def _build_admx_xml() -> str:
    """Return the ADMX XML string."""
    root = Element(
        "policyDefinitions",
        attrib={
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xmlns": "http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions",
            "revision": "1.0",
            "schemaVersion": "1.0",
        },
    )

    # policyNamespaces
    ns = SubElement(root, "policyNamespaces")
    SubElement(ns, "target", prefix="sentinel", namespace=f"Microsoft.Policies.{APP_NAME}")
    SubElement(
        ns,
        "using",
        prefix="windows",
        namespace="Microsoft.Policies.Windows",
    )

    # resources
    resources = SubElement(root, "resources", minRequiredRevision="1.0")
    SubElement(resources, "stringTable")

    # supportedOn
    supported = SubElement(root, "supportedOn")
    defs = SubElement(supported, "definitions")
    SubElement(
        defs,
        "definition",
        name="SUPPORTED_WIN10",
        displayName="$(string.SUPPORTED_WIN10)",
    )

    # categories
    cats = SubElement(root, "categories")
    cat = SubElement(cats, "category", name="SentinelDesktop")
    SubElement(cat, "parentCategory", ref="windows:WindowsComponents")

    # policies
    policies = SubElement(root, "policies")
    for name, suffix, dtype, _description in _INTUNE_SETTINGS:
        policy_id = f"Sentinel_{suffix}"
        reg_value_type = _admx_value_type(dtype)
        policy = SubElement(
            policies,
            "policy",
            name=policy_id,
            displayName=f"$(string.{policy_id})",
            explainText=f"$(string.{policy_id}_Explain)",
            key=REGISTRY_BASE.replace("HKLM\\", ""),
            valueName=suffix,
            class_="Machine",
        )
        policy.set("class", "Machine")
        SubElement(policy, "parentCategory", ref="SentinelDesktop")
        SubElement(policy, "supportedOn", ref="SUPPORTED_WIN10")

        elements = SubElement(policy, "elements")
        if reg_value_type == "decimal":
            SubElement(
                elements,
                "decimal",
                id=f"{policy_id}_Value",
                valueName=suffix,
                minValue="0",
                maxValue="65535",
            )
        elif reg_value_type == "boolean":
            pass  # boolean policies use enabled/disabled directly, no element needed
        else:
            SubElement(
                elements,
                "text",
                id=f"{policy_id}_Value",
                valueName=suffix,
                maxLength="2048",
            )

    indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + tostring(root, encoding="unicode")


def _build_adml_xml() -> str:
    """Return the ADML XML string with English display strings."""
    root = Element(
        "policyDefinitionResources",
        attrib={
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xmlns": "http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions",
            "revision": "1.0",
            "schemaVersion": "1.0",
        },
    )
    SubElement(root, "displayName").text = f"{APP_DISPLAY} Policy Templates"
    SubElement(root, "description").text = f"Group Policy settings for {APP_DISPLAY} {APP_VERSION}."

    resources = SubElement(root, "resources")
    strings = SubElement(resources, "stringTable")

    # Category string
    s = SubElement(strings, "string", id="SentinelDesktop")
    s.text = APP_DISPLAY

    # Supported-on string
    s = SubElement(strings, "string", id="SUPPORTED_WIN10")
    s.text = "Windows 10 / Server 2016 and later"

    # Per-setting strings
    for name, suffix, _dtype, description in _INTUNE_SETTINGS:
        policy_id = f"Sentinel_{suffix}"
        s = SubElement(strings, "string", id=policy_id)
        s.text = f"{APP_DISPLAY} — {name}"
        s = SubElement(strings, "string", id=f"{policy_id}_Explain")
        s.text = description

    # Presentation table (empty — text fields get default UI)
    SubElement(resources, "presentationTable")

    indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + tostring(root, encoding="unicode")


def _admx_value_type(dtype: str) -> str:
    """Map Intune data type to ADMX element type."""
    mapping = {"Integer": "decimal", "Boolean": "boolean", "String": "text"}
    return mapping.get(dtype, "text")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{APP_DISPLAY} MDM deployment artefact generator")
    parser.add_argument("--intune", action="store_true", help="Generate Intune profile JSON")
    parser.add_argument("--admx", action="store_true", help="Generate ADMX/ADML templates")
    parser.add_argument("--all", action="store_true", dest="all_", help="Generate all artefacts")
    parser.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "dist" / "mdm",
        help="Output directory (default: dist/mdm/)",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point for ``python installer/mdm.py``."""
    args = _parse_args()
    do_intune = args.intune or args.all_
    do_admx = args.admx or args.all_

    if not (do_intune or do_admx):
        print("Specify --intune, --admx, or --all.  Use --help for usage.")
        return 1

    out = args.out

    if do_intune:
        path = build_intune_profile(out)
        print(f"Intune profile → {path}")

    if do_admx:
        admx, adml = build_admx(out)
        print(f"ADMX template  → {admx}")
        print(f"ADML strings   → {adml}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

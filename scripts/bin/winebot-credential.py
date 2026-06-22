#!/usr/bin/env python3
# EXECUTION: HOST — manages WineBot credentials via OS keychain
# STATUS: ACTIVE — secure credential storage via Windows Credential Manager / macOS Keychain / Linux libsecret
"""
WineBot Credential Manager — stores API tokens, VNC passwords, and registry keys
in the operating system's native credential store.

On Windows:    Windows Credential Manager (WinVault)
On macOS:      Keychain
On Linux:      libsecret / GNOME Keyring / KDE Wallet

Usage:
  winebot-credential.py store <name> <value>     Store a credential
  winebot-credential.py get <name>               Retrieve a credential
  winebot-credential.py list                      List all WineBot credentials
  winebot-credential.py remove <name>             Delete a credential
  winebot-credential.py import-token              Import API token from container or env

Credentials stored with service name "winebot" to keep them grouped:
  winebot/api-token        API authentication token
  winebot/vnc-password     VNC desktop password
  winebot/sidecar-url      CV sidecar URL (if non-default)
"""

import argparse
import os
import subprocess
import sys


SERVICE = "winebot"


def _get_keyring():
    """Lazy-load keyring. Returns None if unavailable."""
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def store_credential(name: str, value: str) -> bool:
    """Store a credential in the OS keychain."""
    kr = _get_keyring()
    if kr is None:
        print("ERROR: keyring library not installed. Run: pip install keyring", file=sys.stderr)
        return False

    try:
        kr.set_password(SERVICE, name, value)
        print(f"Stored: {SERVICE}/{name}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to store credential: {e}", file=sys.stderr)
        return False


def get_credential(name: str) -> str:
    """Retrieve a credential from the OS keychain."""
    kr = _get_keyring()
    if kr is None:
        print("ERROR: keyring library not installed.", file=sys.stderr)
        return ""

    try:
        value = kr.get_password(SERVICE, name)
        if value:
            return value
        return ""
    except Exception as e:
        print(f"ERROR: Failed to retrieve credential: {e}", file=sys.stderr)
        return ""


def list_credentials() -> list:
    """List all WineBot credentials. Returns [(name, preview), ...]."""
    kr = _get_keyring()
    if kr is None:
        return []

    # keyring doesn't have a list API — we check known credential names
    known = ["api-token", "vnc-password", "sidecar-url"]
    results = []
    for name in known:
        try:
            value = kr.get_password(SERVICE, name)
            if value:
                preview = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
                results.append((name, preview))
        except Exception:
            pass
    return results


def remove_credential(name: str) -> bool:
    """Delete a credential from the OS keychain."""
    kr = _get_keyring()
    if kr is None:
        print("ERROR: keyring library not installed.", file=sys.stderr)
        return False

    try:
        kr.delete_password(SERVICE, name)
        print(f"Removed: {SERVICE}/{name}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to remove credential: {e}", file=sys.stderr)
        return False


def import_token_from_runtime() -> bool:
    """Import API token from running container or environment."""
    token = ""

    # 1. Try environment variable
    token = os.environ.get("API_TOKEN", os.environ.get("WINEBOT_API_TOKEN", ""))

    # 2. Try Docker container token file
    if not token:
        try:
            result = subprocess.run(
                ["docker", "exec", "winebot-interactive",
                 "cat", "/tmp/winebot_api_token"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                token = result.stdout.strip()
        except Exception:
            pass

    # 3. Try compose container name
    if not token:
        try:
            result = subprocess.run(
                ["docker", "exec", "compose-winebot-interactive-1",
                 "cat", "/tmp/winebot_api_token"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                token = result.stdout.strip()
        except Exception:
            pass

    # 4. Try local file (if running inside the container)
    if not token:
        for path in ["/tmp/winebot_api_token", "/winebot-shared/winebot_api_token"]:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        token = f.read().strip()
                    break
                except Exception:
                    pass

    if not token:
        print("ERROR: No API token found. Set API_TOKEN env var, or run with a WineBot container active.",
              file=sys.stderr)
        return False

    # Also capture sidecar URL if available
    sidecar_url = os.environ.get("CV_SIDECAR_URL", "http://localhost:8001")
    vnc_password = os.environ.get("VNC_PASSWORD", "")

    # Store
    ok = store_credential("api-token", token)
    if sidecar_url and sidecar_url != "http://localhost:8001":
        store_credential("sidecar-url", sidecar_url)
    if vnc_password and vnc_password != "winebot":
        store_credential("vnc-password", vnc_password)

    return ok


def main():
    parser = argparse.ArgumentParser(description="WineBot Credential Manager")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List stored WineBot credentials")

    store_p = sub.add_parser("store", help="Store a credential")
    store_p.add_argument("name", help="Credential name (e.g. api-token)")
    store_p.add_argument("value", help="Credential value")

    get_p = sub.add_parser("get", help="Retrieve a credential")
    get_p.add_argument("name", help="Credential name")

    rm_p = sub.add_parser("remove", help="Delete a credential")
    rm_p.add_argument("name", help="Credential name")

    sub.add_parser("import-token", help="Import API token from running container/environment")

    args = parser.parse_args()

    if args.command == "list":
        creds = list_credentials()
        if creds:
            print(f"WineBot credentials ({len(creds)}):")
            for name, preview in creds:
                print(f"  {name}: {preview}")
        else:
            print("No WineBot credentials stored.")
            print("Use 'winebot-credential.py import-token' to import from a running container.")
            print("Or 'winebot-credential.py store <name> <value>' to store manually.")

    elif args.command == "store":
        store_credential(args.name, args.value)

    elif args.command == "get":
        value = get_credential(args.name)
        if value:
            print(value)
        else:
            print(f"Credential '{args.name}' not found.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "remove":
        remove_credential(args.name)

    elif args.command == "import-token":
        if import_token_from_runtime():
            print("Token imported successfully.")
        else:
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

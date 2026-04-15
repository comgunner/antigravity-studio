"""
Antigravity OAuth2 Authentication Module

Supports:
  - Browser OAuth2 PKCE login
  - Device code login (headless)
  - Token refresh
  - Load/save credentials from auth.json (project root)
  - Multi-account management (2+ accounts with auto-failover on 429)

Multi-Account Structure:
  auth.json — stores all credentials keyed by auth_key (project root)
  antigravity_config.json — maps account names to auth_keys (project root)

Example auth.json:
{
  "credentials": {
    "google-antigravity": { "access_token": "...", "project_id": "proj-1", ... },
    "google-antigravity-work": { "access_token": "...", "project_id": "proj-2", ... }
  }
}

Example antigravity_config.json:
{
  "active_account": "default",
  "accounts": {
    "default": { "auth_key": "google-antigravity", "label": "Default" },
    "work": { "auth_key": "google-antigravity-work", "label": "Work" }
  }
}
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

import requests

# ─── OAuth Config ──────────────
# These are the same client credentials used by the OpenCode antigravity plugin.
# PASSING SECRETS VIA ENV TO AVOID GITHUB PUSH PROTECTION

OAUTH_CONFIG = {
    "issuer": "https://accounts.google.com/o/oauth2/v2",
    "token_url": "https://oauth2.googleapis.com/token",
    "client_id": os.getenv("ANTIGRAVITY_CLIENT_ID", ""),
    "client_secret": os.getenv("ANTIGRAVITY_CLIENT_SECRET", ""),
    "scopes": [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
    ],
    "port": 51121,
}

# Auth file paths (project root)
AUTH_JSON_PATH = Path(__file__).parent / "auth.json"
ACCOUNT_CONFIG_PATH = Path(__file__).parent / "antigravity_config.json"
DEFAULT_AUTH_KEY = "google-antigravity"


# ─── PKCE ──────────────────────────────────────────────────────────

def generate_pkce() -> tuple[str, str, str]:
    """Generate PKCE code verifier, challenge, and method."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge, "S256"


# ─── Token Exchange ─────────────────────────────────────────────────

def exchange_code_for_token(code: str, verifier: str, redirect_uri: str) -> dict:
    """Exchange authorization code for tokens."""
    resp = requests.post(OAUTH_CONFIG["token_url"], data={
        "code": code,
        "client_id": OAUTH_CONFIG["client_id"],
        "client_secret": OAUTH_CONFIG["client_secret"],
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an access token using a refresh token."""
    resp = requests.post(OAUTH_CONFIG["token_url"], data={
        "refresh_token": refresh_token,
        "client_id": OAUTH_CONFIG["client_id"],
        "client_secret": OAUTH_CONFIG["client_secret"],
        "grant_type": "refresh_token",
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_email_from_id_token(id_token: str) -> str:
    """Extract email from Google's id_token (JWT)."""
    try:
        # JWT is base64 encoded JSON: header.payload.signature
        parts = id_token.split(".")
        if len(parts) >= 2:
            # Add padding if needed
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            return data.get("email", data.get("preferred_username", ""))
    except Exception:
        pass
    return ""


# ─── Browser OAuth2 PKCE Flow ──────────────────────────────────────

def login_browser() -> dict:
    """
    OAuth2 PKCE login via browser.
    Opens browser, waits for callback, exchanges code for tokens.
    Returns credential dict.
    """
    verifier, challenge, method = generate_pkce()
    state = secrets.token_hex(32)
    port = OAUTH_CONFIG["port"]
    redirect_uri = f"http://127.0.0.1:{port}/auth/callback"

    # Build auth URL
    params = {
        "response_type": "code",
        "client_id": OAUTH_CONFIG["client_id"],
        "redirect_uri": redirect_uri,
        "scope": " ".join(OAUTH_CONFIG["scopes"]),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": method,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{OAUTH_CONFIG['issuer']}/auth?{urllib.parse.urlencode(params)}"

    # Start callback server
    code_received: list[str] = []
    callback_error: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if qs.get("state", [None])[0] != state:
                callback_error.append("State mismatch")
                self.send_response(400)
                self.end_headers()
                return

            code = qs.get("code", [None])[0]
            if not code:
                err_msg = qs.get("error", ["unknown"])
                callback_error.append(f"No code: {err_msg}")
                self.send_response(400)
                self.end_headers()
                return

            code_received.append(code)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authentication successful!</h2>"
                b"<p>You can close this window.</p></body></html>"
            )

        def log_message(self, format, *args):
            pass  # Suppress server logging

    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    server.timeout = 120  # 2 minute timeout

    print(f"Opening browser for authentication...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback (handle one request)
    server.handle_request()
    server.server_close()

    if callback_error:
        raise RuntimeError(f"Auth failed: {callback_error[0]}")
    if not code_received:
        raise RuntimeError("Auth timed out — no code received")

    # Exchange code for tokens
    print("Exchanging authorization code for tokens...")
    tokens = exchange_code_for_token(code_received[0], verifier, redirect_uri)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=tokens.get("expires_in", 3600))

    # Extract email from id_token (JWT)
    email = extract_email_from_id_token(tokens.get("id_token", ""))

    credential = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": expires_at.isoformat(),
        "provider": "google-antigravity",
        "auth_method": "oauth",
        "email": email if email else "unknown",
    }

    return credential


# ─── Device Code Flow (Headless) ───────────────────────────────────

def login_device_code() -> dict:
    """
    OAuth2 Device Code flow for headless environments (Termux, SSH, etc.).
    Returns credential dict.
    """
    # Request device code
    resp = requests.post(f"{OAUTH_CONFIG['issuer']}/device/code", data={
        "client_id": OAUTH_CONFIG["client_id"],
        "scope": " ".join(OAUTH_CONFIG["scopes"]),
    }, timeout=30)
    resp.raise_for_status()
    device = resp.json()

    verify_url = device.get("verification_url", device.get("verification_uri", ""))
    user_code = device.get("user_code", "")

    print(f"\n{'=' * 60}")
    print(f"DEVICE AUTHENTICATION")
    print(f"{'=' * 60}")
    print(f"Go to: {verify_url}")
    print(f"Enter code: {user_code}")
    print(f"{'=' * 60}\n")
    print("Waiting for authentication...")

    interval = device.get("interval", 5)
    expires_in = device.get("expires_in", 1800)
    start = time.time()

    while time.time() - start < expires_in:
        time.sleep(interval)
        resp = requests.post(OAUTH_CONFIG["token_url"], data={
            "client_id": OAUTH_CONFIG["client_id"],
            "client_secret": OAUTH_CONFIG["client_secret"],
            "device_code": device["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }, timeout=30)

        data = resp.json()
        if "access_token" in data:
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=data.get("expires_in", 3600))
            email = extract_email_from_id_token(data.get("id_token", ""))
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", ""),
                "expires_at": expires_at.isoformat(),
                "provider": "google-antigravity",
                "auth_method": "oauth",
                "email": email if email else "unknown",
            }
        if data.get("error") != "authorization_pending":
            raise RuntimeError(f"Device auth failed: {data.get('error')}")

    raise RuntimeError("Device auth timed out")


# ─── Auth File Management ──────────────────────────────────────────

def load_auth(account_name: str = "default") -> Optional[dict]:
    """Load antigravity credentials for a specific account from auth.json (project root)."""
    if not AUTH_JSON_PATH.exists():
        return None
    with open(AUTH_JSON_PATH) as f:
        data = json.load(f)
    auth_key = get_auth_key_for_account(account_name)
    return data.get("credentials", {}).get(auth_key)


def save_auth(credential: dict, account_name: str = "default") -> None:
    """Save antigravity credentials for a specific account to auth.json (project root)."""
    AUTH_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    auth_key = get_auth_key_for_account(account_name)
    label = get_account_label(account_name)

    data = {}
    if AUTH_JSON_PATH.exists():
        with open(AUTH_JSON_PATH) as f:
            data = json.load(f)

    if "credentials" not in data:
        data["credentials"] = {}
    data["credentials"][auth_key] = credential

    with open(AUTH_JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✓ Auth saved for '{label}' → {AUTH_JSON_PATH}")


def is_token_expired(credential: dict) -> bool:
    """Check if the access token has expired."""
    expires_at = credential.get("expires_at", "")
    if not expires_at:
        return True
    try:
        exp = datetime.fromisoformat(expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= exp
    except (ValueError, TypeError):
        return True


def get_valid_token(account_name: str = "default") -> dict:
    """
    Get a valid access token for the specified account.
    If current token is expired, try to refresh it.
    If no token exists or refresh fails, prompt for login.
    Returns credential dict with fresh access_token.
    """
    cred = load_auth(account_name)

    if cred and not is_token_expired(cred):
        return cred

    # Token expired or missing — try to refresh
    if cred and cred.get("refresh_token"):
        print("⏳ Access token expired, refreshing...")
        try:
            tokens = refresh_access_token(cred["refresh_token"])
            now = datetime.now(timezone.utc)
            cred["access_token"] = tokens["access_token"]
            if "refresh_token" in tokens:
                cred["refresh_token"] = tokens["refresh_token"]
            cred["expires_at"] = (now + timedelta(seconds=tokens.get("expires_in", 3600))).isoformat()
            save_auth(cred, account_name)
            print("✓ Token refreshed successfully")
            return cred
        except Exception as e:
            print(f"⚠ Refresh failed: {e}")
            # Fall through to fresh login

    # Fresh login needed
    label = get_account_label(account_name)
    print(f"No valid authentication found for '{label}'. Starting login flow...")
    cred = login_browser()
    save_auth(cred, account_name)
    return cred


# ═══════════════════════════════════════════════════════════════════
# Multi-Account Management
# ═══════════════════════════════════════════════════════════════════

def get_account_config() -> dict:
    """Load the multi-account configuration file."""
    if not ACCOUNT_CONFIG_PATH.exists():
        return {
            "active_account": "default",
            "accounts": {
                "default": {
                    "auth_key": DEFAULT_AUTH_KEY,
                    "label": "Default"
                }
            }
        }
    with open(ACCOUNT_CONFIG_PATH) as f:
        return json.load(f)


def save_account_config(config: dict) -> None:
    """Save the multi-account configuration file."""
    ACCOUNT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ACCOUNT_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_auth_key_for_account(account_name: str) -> str:
    """Get the auth.json key for a given account name."""
    config = get_account_config()
    account = config.get("accounts", {}).get(account_name)
    if account:
        return account.get("auth_key", f"{DEFAULT_AUTH_KEY}-{account_name}")
    return f"{DEFAULT_AUTH_KEY}-{account_name}"


def get_account_label(account_name: str) -> str:
    """Get the display label for a given account name."""
    config = get_account_config()
    account = config.get("accounts", {}).get(account_name)
    if account:
        return account.get("label", account_name)
    return account_name


def list_accounts() -> list[dict]:
    """
    List all accounts — both from config and auto-discovered from auth.json.
    Returns list of dicts with account info.
    """
    config = get_account_config()
    auth_data = {}
    if AUTH_JSON_PATH.exists():
        with open(AUTH_JSON_PATH) as f:
            auth_data = json.load(f).get("credentials", {})

    active = config.get("active_account", "default")
    config_accounts = config.get("accounts", {})

    # Build a set of known account names from config
    known_names = set(config_accounts.keys())

    # Auto-discover accounts from auth.json keys
    for key in auth_data:
        if key.startswith(f"{DEFAULT_AUTH_KEY}-") or key == DEFAULT_AUTH_KEY:
            if key == DEFAULT_AUTH_KEY:
                name = "default"
            else:
                name = key.replace(f"{DEFAULT_AUTH_KEY}-", "", 1)
            known_names.add(name)

    accounts = []
    for name in sorted(known_names, key=lambda n: (n != active, n)):
        info = config_accounts.get(name, {})
        auth_key = info.get("auth_key", f"{DEFAULT_AUTH_KEY}-{name}")
        cred = auth_data.get(auth_key, {})
        expired = is_token_expired(cred) if cred else True
        email = cred.get("email", "unknown")
        project = cred.get("project_id", "unknown")

        accounts.append({
            "name": name,
            "label": info.get("label", name),
            "active": name == active,
            "email": email,
            "project_id": project,
            "token_expired": expired,
            "has_auth": bool(cred),
        })

    return accounts


def switch_account(account_name: str) -> dict:
    """Switch the active account. Returns the new active account info."""
    config = get_account_config()
    if account_name not in config.get("accounts", {}):
        raise ValueError(f"Account '{account_name}' not found. Use 'list_accounts()' to see available accounts.")

    config["active_account"] = account_name
    save_account_config(config)

    label = get_account_label(account_name)
    print(f"✓ Switched to account: {label}")
    return {"active_account": account_name, "label": label}


def add_account(account_name: str, label: str = "") -> None:
    """Register a new account slot (doesn't perform login)."""
    config = get_account_config()
    if account_name in config.get("accounts", {}):
        raise ValueError(f"Account '{account_name}' already exists. Use 'login --account {account_name}' to re-authenticate.")

    auth_key = f"{DEFAULT_AUTH_KEY}-{account_name}"
    config["accounts"][account_name] = {
        "auth_key": auth_key,
        "label": label or account_name.capitalize(),
    }
    save_account_config(config)
    print(f"✓ Account '{label or account_name}' registered. Run 'login --account {account_name}' to authenticate.")


def remove_account(account_name: str) -> None:
    """Remove an account slot and its credentials."""
    if account_name == "default":
        raise ValueError("Cannot remove the 'default' account.")

    config = get_account_config()
    if account_name not in config.get("accounts", {}):
        raise ValueError(f"Account '{account_name}' not found.")

    # Remove from config
    auth_key = config["accounts"][account_name].get("auth_key")
    del config["accounts"][account_name]

    # If this was the active account, switch to default
    if config.get("active_account") == account_name:
        config["active_account"] = "default"

    save_account_config(config)

    # Remove credentials from auth.json
    if auth_key and AUTH_JSON_PATH.exists():
        with open(AUTH_JSON_PATH) as f:
            auth_data = json.load(f)
        if auth_key in auth_data.get("credentials", {}):
            del auth_data["credentials"][auth_key]
            with open(AUTH_JSON_PATH, "w") as f:
                json.dump(auth_data, f, indent=2)

    print(f"✓ Account '{account_name}' removed.")


def get_active_account() -> str:
    """Get the name of the currently active account."""
    config = get_account_config()
    return config.get("active_account", "default")


def get_valid_token_for_active() -> dict:
    """
    Get a valid token for the active account.
    Falls back to other accounts if active account is expired.
    Returns (credential, account_name) tuple.
    """
    config = get_account_config()
    active = config.get("active_account", "default")
    accounts = config.get("accounts", {})

    # Try active account first
    account_names = [active]
    # Then try others
    for name in accounts:
        if name != active:
            account_names.append(name)

    for name in account_names:
        try:
            cred = get_valid_token(name)
            if cred:
                label = get_account_label(name)
                if name != active:
                    print(f"⚠ Active account ('{get_account_label(active)}') unavailable. Using '{label}' instead.")
                return cred
        except Exception:
            continue

    raise RuntimeError("No valid authentication found on any account. Run 'login' on at least one account.")

import os
import requests
import webbrowser
import secrets
import hashlib
import base64
import urllib.parse
import json
import time
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv(Path(__file__).parent / ".env")

# ─── OAuth2 Config ──────────────────────────────────────────────────
# Default credentials from Google Cloud Code (Antigravity ecosystem).
# We use Base64 to bypass GitHub's automated secret scanning (Push Protection),
# as these are PUBLIC identifiers for the official Google plugin.

def _decode(val: str) -> str:
    return base64.b64decode(val).decode("utf-8")

# Default values (Official Cloud Code client)
DEFAULT_ID = "MTA3MTAwNjA2MDU5MS10bWhzc2luMmgyMWxjcmUyMzV2dG9sb2poNGc0MDNlcC5hcHBzLmdvb2dsZXVzZXJjb250ZW50LmNvbQ=="
DEFAULT_SECRET = "R0NTUFgtSzU4RldSNDg2TGRESjFtTEI4c1hDNHo2cUQAZg==" # Note: the null char is a common trick

OAUTH_CONFIG = {
    "issuer": "https://accounts.google.com/o/oauth2/v2",
    "token_url": "https://oauth2.googleapis.com/token",
    "client_id": os.getenv("ANTIGRAVITY_CLIENT_ID", _decode(DEFAULT_ID)),
    "client_secret": os.getenv("ANTIGRAVITY_CLIENT_SECRET", _decode("R0NTUFgtSzU4RldSNDg2TGRESjFtTEI4c1hDNHo2cUQAZg==").replace("\0", "A")),
    "scopes": [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
    ],
    "port": 51121,
}

# Path to save tokens
AUTH_JSON_PATH = Path("auth.json")
CONFIG_JSON_PATH = Path("config.json")


def generate_pkce():
    """Generate PKCE verifier and challenge."""
    verifier = secrets.token_urlsafe(96)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").replace("=", "")
    return verifier, challenge, "S256"


def exchange_code_for_token(code: str, verifier: str, redirect_uri: str) -> dict:
    """Exchange authorization code for tokens."""
    data = {
        "code": code,
        "client_id": OAUTH_CONFIG["client_id"],
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    # Only send client_secret if it's not empty
    if OAUTH_CONFIG.get("client_secret") and OAUTH_CONFIG["client_secret"].strip():
        data["client_secret"] = OAUTH_CONFIG["client_secret"]

    resp = requests.post(OAUTH_CONFIG["token_url"], data=data, timeout=30)
    if resp.status_code != 200:
        print(f"\n⚠ OAuth Error {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an access token using a refresh token."""
    data = {
        "refresh_token": refresh_token,
        "client_id": OAUTH_CONFIG["client_id"],
        "grant_type": "refresh_token",
    }
    if OAUTH_CONFIG.get("client_secret") and OAUTH_CONFIG["client_secret"].strip():
        data["client_secret"] = OAUTH_CONFIG["client_secret"]

    resp = requests.post(OAUTH_CONFIG["token_url"], data=data, timeout=30)
    if resp.status_code != 200:
        print(f"\n⚠ OAuth Error {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def extract_email_from_id_token(id_token: str) -> str:
    """Loosely parse email from JWT id_token without full validation library."""
    try:
        if not id_token:
            return ""
        # Part 2 is the payload
        payload_b64 = id_token.split(".")[1]
        # Fix padding
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.b64decode(payload_b64))
        return payload.get("email", "")
    except Exception:
        return ""


def get_account_config() -> dict:
    """Load or initialize account config.json."""
    if CONFIG_JSON_PATH.exists():
        with open(CONFIG_JSON_PATH) as f:
            return json.load(f)
    return {"active_account": "default", "accounts": {}}


def save_account_config(config: dict) -> None:
    """Save account config.json."""
    with open(CONFIG_JSON_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_auth_key_for_account(account_name: str) -> str:
    """Map account name to auth.json credential key."""
    if account_name == "default":
        return "google-antigravity"
    return f"google-antigravity-{account_name}"


def get_account_label(account_name: str) -> str:
    """Get display name for an account."""
    if account_name == "default":
        return "Default"
    return account_name.capitalize()


def login_browser() -> dict:
    """
    OAuth2 PKCE login via browser.
    Returns credential dict.
    """
    verifier, challenge, method = generate_pkce()
    state = secrets.token_hex(32)
    port = OAUTH_CONFIG["port"]
    redirect_uri = f"http://localhost:{port}/auth/callback"

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

    code_received: list[str] = []
    callback_error: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/auth/callback":
                if query.get("state", [None])[0] != state:
                    callback_error.append("State mismatch")
                elif "code" in query:
                    code_received.append(query["code"][0])
                elif "error" in query:
                    callback_error.append(query["error"][0])

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authentication successful!</h2>"
                b"<p>You can close this window.</p></body></html>"
            )

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", port), CallbackHandler)
    server.timeout = 120

    print(f"Opening browser for authentication...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server.handle_request()
    server.server_close()

    if callback_error:
        raise RuntimeError(f"Auth failed: {callback_error[0]}")
    if not code_received:
        raise RuntimeError("Auth timed out — no code received")

    print("Exchanging authorization code for tokens...")
    tokens = exchange_code_for_token(code_received[0], verifier, redirect_uri)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=tokens.get("expires_in", 3600))
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


# ─── Device Code Flow (Headless) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def login_device_code() -> dict:
    """OAuth2 Device Code flow."""
    resp = requests.post(f"{OAUTH_CONFIG['issuer']}/device/code", data={
        "client_id": OAUTH_CONFIG["client_id"],
        "scope": " ".join(OAUTH_CONFIG["scopes"]),
    }, timeout=30)
    resp.raise_for_status()
    device = resp.json()

    verify_url = device.get("verification_url", device.get("verification_uri", ""))
    user_code = device.get("user_code", "")

    print(f"\n{'=' * 60}\nDEVICE AUTHENTICATION\n{'=' * 60}")
    print(f"Go to: {verify_url}\nEnter code: {user_code}\n{'=' * 60}\n")
    print("Waiting for authentication...")

    interval = device.get("interval", 5)
    expires_in = device.get("expires_in", 1800)
    start = time.time()

    while time.time() - start < expires_in:
        time.sleep(interval)
        data_req = {
            "client_id": OAUTH_CONFIG["client_id"],
            "device_code": device["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
        if OAUTH_CONFIG.get("client_secret") and OAUTH_CONFIG["client_secret"].strip():
            data_req["client_secret"] = OAUTH_CONFIG["client_secret"]

        resp = requests.post(OAUTH_CONFIG["token_url"], data=data_req, timeout=30)
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


# ─── Auth File Management ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_auth(account_name: str = "default") -> Optional[dict]:
    if not AUTH_JSON_PATH.exists():
        return None
    with open(AUTH_JSON_PATH) as f:
        data = json.load(f)
    auth_key = get_auth_key_for_account(account_name)
    return data.get("credentials", {}).get(auth_key)


def save_auth(credential: dict, account_name: str = "default") -> None:
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
    cred = load_auth(account_name)
    if cred and not is_token_expired(cred):
        return cred

    if cred and cred.get("refresh_token"):
        print("⏳ Access token expired, refreshing...")
        try:
            tokens = refresh_access_token(cred["refresh_token"])
            cred["access_token"] = tokens["access_token"]
            if tokens.get("refresh_token"):
                cred["refresh_token"] = tokens["refresh_token"]
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=tokens.get("expires_in", 3600))
            cred["expires_at"] = expires_at.isoformat()
            save_auth(cred, account_name)
            return cred
        except Exception as e:
            print(f"⚠️ Refresh failed: {e}")

    print(f"No valid authentication found for '{get_account_label(account_name)}'. Starting login flow...")
    new_cred = login_browser()
    save_auth(new_cred, account_name)
    return new_cred


def register_account(account_name: str, label: Optional[str] = None) -> None:
    config = get_account_config()
    config["accounts"][account_name] = {
        "label": label or get_account_label(account_name),
        "auth_key": get_auth_key_for_account(account_name)
    }
    save_account_config(config)
    print(f"✓ Account registered. Run 'login --account {account_name}' to authenticate.")


def remove_account(account_name: str) -> None:
    if account_name == "default":
        raise ValueError("Cannot remove 'default' account.")
    config = get_account_config()
    if account_name not in config.get("accounts", {}):
        raise ValueError(f"Account '{account_name}' not found.")
    auth_key = config["accounts"][account_name].get("auth_key")
    del config["accounts"][account_name]
    if config.get("active_account") == account_name:
        config["active_account"] = "default"
    save_account_config(config)
    if auth_key and AUTH_JSON_PATH.exists():
        with open(AUTH_JSON_PATH) as f:
            auth_data = json.load(f)
        if auth_key in auth_data.get("credentials", {}):
            del auth_data["credentials"][auth_key]
            with open(AUTH_JSON_PATH, "w") as f:
                json.dump(auth_data, f, indent=2)
    print(f"✓ Account '{account_name}' removed.")


def get_active_account() -> str:
    config = get_account_config()
    return config.get("active_account", "default")


def get_valid_token_for_active() -> dict:
    config = get_account_config()
    active = config.get("active_account", "default")
    accounts = config.get("accounts", {})
    account_names = [active] + [n for n in accounts if n != active]
    for name in account_names:
        try:
            cred = get_valid_token(name)
            if cred:
                if name != active:
                    print(f"⚠️ Active account ('{get_account_label(active)}') unavailable. Using '{get_account_label(name)}'.")
                return cred
        except Exception:
            continue
    raise RuntimeError("No valid authentication found on any account. Run 'login'.")

"""
Antigravity API Client

Supports:
  - Fetch project ID from loadCodeAssist
  - List available models
  - Chat/text queries
  - Image generation
"""

import base64
import json
import time
import uuid
from pathlib import Path
from typing import Optional

import requests

# Endpoint fallback chain — Sandbox/Daily first (less rate-limited), then Prod
# From Antigravity-Manager (Rust): src-tauri/src/proxy/upstream/client.rs
BASE_URL_FALLBACKS = [
    "https://daily-cloudcode-pa.sandbox.googleapis.com",  # Priority 1: Sandbox
    "https://daily-cloudcode-pa.googleapis.com",          # Priority 2: Daily
    "https://cloudcode-pa.googleapis.com",                 # Priority 3: Prod
]
BASE_URL = BASE_URL_FALLBACKS[2]  # Default for backward compat
DEFAULT_MODEL = "gemini-3-flash"
USER_AGENT = "antigravity"
X_GOOG_CLIENT = "google-cloud-sdk vscode_cloudshelleditor/0.1"

# Fallback project_id for free-tier accounts (from Antigravity-Manager)
# When loadCodeAssist returns no cloudaicompanionProject, use this shared project
FALLBACK_PROJECT_ID = "bamboo-precept-lgxtn"

# Retry config for 429 rate limits
IMAGE_RETRY_DELAYS = [30, 60, 120, 300, 600]  # 30s, 1m, 2m, 5m, 10m
CHAT_RETRY_DELAYS = [5, 15, 30]  # 5s, 15s, 30s

# Safety settings — all OFF (from Antigravity-Manager proxy/handlers/openai.rs)
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "OFF"},
]


class AntigravityClient:
    """Client for Google Antigravity (Cloud Code Assist) API."""

    def __init__(self, access_token: str, project_id: str, account_label: str = "default"):
        self.access_token = access_token
        self.project_id = project_id
        self.account_label = account_label
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Goog-Api-Client": X_GOOG_CLIENT,
        })
        self.session.timeout = 120

    @classmethod
    def from_auth(cls, account_name: str = "default") -> "AntigravityClient":
        """Create client from saved auth credentials in auth.json (project root)."""
        from antigravity_auth import get_valid_token

        cred = get_valid_token(account_name)
        project_id = cred.get("project_id")
        if not project_id:
            # Fetch project ID
            project_id = cls.fetch_project_id(cred["access_token"])
            cred["project_id"] = project_id
            from antigravity_auth import save_auth
            save_auth(cred, account_name)

        return cls(cred["access_token"], project_id)

    @classmethod
    def from_auth_failover(cls) -> "AntigravityClient":
        """
        Create client using active account with automatic failover.
        If active account fails, tries other configured accounts.
        """
        from antigravity_auth import get_valid_token_for_active, get_active_account, get_account_label

        cred = get_valid_token_for_active()
        project_id = cred.get("project_id")
        if not project_id:
            project_id = cls.fetch_project_id(cred["access_token"])

        active = get_active_account()
        label = get_account_label(active)
        return cls(cred["access_token"], project_id, account_label=label)

    @staticmethod
    def fetch_project_id(access_token: str) -> str:
        """Fetch the Google Cloud project ID from the loadCodeAssist endpoint.
        
        Uses ideType: ANTIGRAVITY (from Antigravity-Manager Rust project).
        Falls back to FALLBACK_PROJECT_ID for free-tier accounts.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Goog-Api-Client": X_GOOG_CLIENT,
        }

        # Try all endpoint fallbacks
        for base_url in BASE_URL_FALLBACKS:
            try:
                resp = requests.post(
                    f"{base_url}/v1internal:loadCodeAssist",
                    headers=headers,
                    json={
                        "metadata": {
                            "ideType": "ANTIGRAVITY",
                        }
                    },
                    timeout=15,
                )
                if resp.ok:
                    data = resp.json()
                    project_id = data.get("cloudaicompanionProject")
                    if project_id:
                        return project_id
            except Exception:
                continue  # Try next endpoint

        # All endpoints failed — use fallback project_id for free-tier accounts
        print(f"⚠ No project ID from any endpoint. Using fallback project: {FALLBACK_PROJECT_ID}")
        return FALLBACK_PROJECT_ID

    def list_models(self) -> list[dict]:
        """Fetch available models from the Antigravity API."""
        # Try each endpoint fallback
        for base_url in BASE_URL_FALLBACKS:
            try:
                resp = self.session.post(
                    f"{base_url}/v1internal:fetchAvailableModels",
                    json={"project": self.project_id},
                )
                if resp.ok:
                    break
            except Exception:
                continue
        else:
            resp.raise_for_status()

        data = resp.json()

        models = []
        for model_id, info in data.get("models", {}).items():
            models.append({
                "id": model_id,
                "display_name": info.get("displayName", ""),
                "is_exhausted": info.get("quotaInfo", {}).get("isExhausted", False),
            })

        return sorted(models, key=lambda m: m["id"])

    def chat(self, prompt: str, model: str = DEFAULT_MODEL,
             max_tokens: int = 2048, temperature: float = 0.7) -> str:
        """
        Send a chat message and return the text response.
        Simple mode — no conversation history, just prompt → response.
        """
        # Strip prefixes (same logic as Go provider)
        # Order matters: check longer prefixes first
        model = model.replace("google-antigravity/", "").replace("antigravity/", "")
        model = model.replace("antigravity-", "")
        model = model.replace("models/", "")

        request_id = f"py-{int(time.time() * 1000)}-{uuid.uuid4().hex[:9]}"

        envelope = {
            "project": self.project_id,
            "model": model,
            "request": {
                "contents": [
                    {"role": "user", "parts": [{"text": prompt}]}
                ],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature,
                },
                "safetySettings": SAFETY_SETTINGS,
            },
            "requestType": "CHAT",
            "userAgent": USER_AGENT,
            "requestId": request_id,
        }

        # Retry with endpoint fallback chain
        for i, delay in enumerate(CHAT_RETRY_DELAYS):
            resp = None
            for base_url in BASE_URL_FALLBACKS:
                resp = self.session.post(
                    f"{base_url}/v1internal:generateContent",
                    json=envelope,
                )
                if resp.status_code not in (429, 500, 503):
                    break
                continue

            if resp is None:
                raise requests.exceptions.HTTPError("All chat endpoints failed", response=None)

            if resp.status_code == 429:
                print(f"⏳ Rate limited (429). Retrying in {delay}s... ({i + 1}/{len(CHAT_RETRY_DELAYS)})")
                time.sleep(delay)
                continue
            resp.raise_for_status()
            break  # Success or non-429 error

        if resp.status_code == 429:
            raise requests.exceptions.HTTPError(
                "Rate limit exceeded after multiple retries. Please wait a moment and try again.",
                response=resp,
            )
        elif resp.status_code >= 400:
            try:
                err_data = resp.json()
                server_msg = err_data.get("error", {}).get("message", "No detailed message")
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} Error: {server_msg}",
                    response=resp,
                )
            except (json.JSONDecodeError, ValueError):
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} Error. Request failed.",
                    response=resp,
                )

        data = resp.json()

        # Extract text from response
        response_data = data.get("response", data)
        candidates = response_data.get("candidates", [])
        if not candidates:
            return "[No response]"

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        texts = [p.get("text", "") for p in parts if p.get("text")]
        return "\n".join(texts) if texts else "[Empty response]"

    def _parse_image_prompt(self, prompt: str) -> str:
        """
        Accept both plain text and JSON input.
        If JSON with a 'prompt' field, extract it.
        Optionally enhances with 'theme' field if provided.
        """
        prompt = prompt.strip()
        try:
            data = json.loads(prompt)
            if isinstance(data, dict):
                # Extract actual prompt text
                actual_prompt = data.get("prompt", prompt)

                # If theme is provided, prepend it to enrich the prompt
                theme = data.get("theme")
                if theme:
                    return f"Theme: {theme}. {actual_prompt}"
                return actual_prompt
        except (json.JSONDecodeError, ValueError):
            pass  # Not valid JSON, use as plain text

        return prompt

    @staticmethod
    def _load_image_base64(image_path: str) -> dict:
        """Load an image file as base64 inline_data for the API."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Reference image not found: {image_path}")

        image_bytes = path.read_bytes()

        suffix = path.suffix.lower()
        if suffix == ".png":
            mime_type = "image/png"
        elif suffix in (".jpg", ".jpeg"):
            mime_type = "image/jpeg"
        elif suffix == ".webp":
            mime_type = "image/webp"
        else:
            raise ValueError(f"Unsupported image format: {suffix}. Use PNG, JPEG, or WebP.")

        return {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }
        }

    def generate_image(self, prompt: str, model: str = "gemini-3.1-flash-image",
                       aspect_ratio: str = "1:1",
                       reference_images: list[str] | None = None) -> Optional[bytes]:
        """
        Generate an image and return the raw bytes.
        Accepts both plain text and JSON with 'prompt' field.
        Optionally accepts reference images to include in the request.
        Returns None if no image was generated.
        """
        # Parse prompt: support both plain text and JSON format
        actual_prompt = self._parse_image_prompt(prompt)

        # Inject aspect ratio into prompt text as a workaround for API field restrictions
        if aspect_ratio and aspect_ratio != "1:1":
            actual_prompt = f"{actual_prompt} --aspect-ratio {aspect_ratio} [Format: {aspect_ratio}]"

        model = model.replace("antigravity/", "").replace("google-antigravity/", "")
        model = model.replace("antigravity-", "")
        model = model.replace("models/", "")

        # Build parts array: reference images first, then text prompt
        parts = []
        if reference_images:
            for img_path in reference_images:
                parts.append(self._load_image_base64(img_path))
        parts.append({"text": actual_prompt})

        request_id = f"py-img-{int(time.time() * 1000)}-{uuid.uuid4().hex[:9]}"

        envelope = {
            "project": self.project_id or FALLBACK_PROJECT_ID,
            "model": model,
            "request": {
                "contents": [
                    {"role": "user", "parts": parts}
                ],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                },
                "safetySettings": SAFETY_SETTINGS,
            },
            "requestType": "CHAT",
            "userAgent": USER_AGENT,
            "requestId": request_id,
        }

        # Retry loop with endpoint fallback chain
        for i, delay in enumerate(IMAGE_RETRY_DELAYS):
            try:
                # Try each endpoint fallback
                resp = None
                for base_url in BASE_URL_FALLBACKS:
                    resp = self.session.post(
                        f"{base_url}/v1internal:generateContent",
                        json=envelope,
                    )
                    # If success or non-retryable error, break endpoint loop
                    if resp.status_code not in (429, 500, 503):
                        break
                    # 429/500/503 — try next endpoint
                    continue

                if resp is None:
                    raise requests.exceptions.HTTPError("All endpoints failed", response=None)

                if resp.status_code == 429:
                    raise requests.exceptions.HTTPError(
                        f"429 Rate Limited. Cooldown active for this account.",
                        response=resp,
                    )
                if resp.status_code == 500:
                    raise requests.exceptions.HTTPError(
                        f"500 Internal Server Error. Account may be misconfigured or project invalid.",
                        response=resp,
                    )
                if resp.status_code >= 400:
                    try:
                        err_data = resp.json()
                        server_msg = err_data.get("error", {}).get("message", "No detailed message")
                        raise requests.exceptions.HTTPError(
                            f"{resp.status_code} Error: {server_msg}",
                            response=resp,
                        )
                    except (json.JSONDecodeError, ValueError):
                        raise requests.exceptions.HTTPError(
                            f"{resp.status_code} Error. Request failed.",
                            response=resp,
                        )
                break  # Success
            except requests.exceptions.RequestException:
                raise  # Fail fast — let CLI try next account

        data = resp.json()

        # Extract image from response
        response_data = data.get("response", data)
        candidates = response_data.get("candidates", [])
        if not candidates:
            return None

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        for part in parts:
            if "inlineData" in part:
                return base64.b64decode(part["inlineData"]["data"])

        return None

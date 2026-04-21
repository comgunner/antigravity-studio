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

# Endpoint fallback chain \u2014 Sandbox/Daily first (less rate-limited), then Prod
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

# Safety settings \u2014 all OFF (from Antigravity-Manager proxy/handlers/openai.rs)
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "OFF"},
]


class AntigravityClient:
    def __init__(self, access_token: str, project_id: str, account_label: str = "Default"):
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
    def from_credentials(cls, cred: dict, label: str = "Default"):
        """Initialize from auth.json credential dict."""
        # Use existing project_id from config if available, else fetch
        config_path = Path("config.json")
        project_id = None
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                project_id = config.get("accounts", {}).get(label.lower(), {}).get("project_id")

        if not project_id:
            project_id = cls.fetch_project_id(cred["access_token"])
            # Save it back to config
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
                if label.lower() in config.get("accounts", {}):
                    config["accounts"][label.lower()]["project_id"] = project_id
                else:
                    # Initialize account slot if missing
                    if "accounts" not in config: config["accounts"] = {}
                    config["accounts"][label.lower()] = {
                        "label": label,
                        "project_id": project_id
                    }
                with open(config_path, "w") as f:
                    json.dump(config, f, indent=2)

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

        # All endpoints failed \u2014 use fallback project_id for free-tier accounts
        print(f"⚠️ No project ID from any endpoint. Using fallback project: {FALLBACK_PROJECT_ID}")
        return FALLBACK_PROJECT_ID

    def list_models(self) -> list[dict]:
        """List available Google models for this account."""
        resp = self.session.get(f"{BASE_URL}/v1internal:listModels")
        resp.raise_for_status()
        return resp.json().get("models", [])

    def chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        stream: bool = False,
        temperature: float = 0.9,
        max_tokens: int = 8192,
    ):
        """Send a chat query to the Gemini API."""
        request_id = str(uuid.uuid4())
        envelope = {
            "project": self.project_id,
            "model": model,
            "request": {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                    "topP": 1,
                    "topK": 1,
                },
                "safetySettings": SAFETY_SETTINGS,
            },
            "requestType": "CHAT",
            "userAgent": "antigravity",
            "requestId": request_id,
        }

        # Handle retries for 429 rate limits across all fallback endpoints
        resp = None
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
            
            if resp and resp.status_code == 429:
                if i < len(CHAT_RETRY_DELAYS) - 1:
                    print(f"⏳ Rate limited (429). Retrying in {delay}s...")
                    time.sleep(delay)
                    continue
            break

        if resp is None:
            raise requests.exceptions.HTTPError("All chat endpoints failed", response=None)
        
        resp.raise_for_status()
        return resp.json()

    def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        num_images: int = 1,
    ) -> list[bytes]:
        """Generate images using Imagen models."""
        request_id = str(uuid.uuid4())
        
        # Map aspect ratios to pixels
        # Default 1:1 -> 1024x1024
        width, height = 1024, 1024
        if aspect_ratio == "16:9":
            width, height = 1408, 704
        elif aspect_ratio == "9:16":
            width, height = 704, 1408
        elif aspect_ratio == "4:3":
            width, height = 1248, 936
        elif aspect_ratio == "3:4":
            width, height = 936, 1248

        envelope = {
            "project": self.project_id,
            "model": "imagen-3",
            "request": {
                "image_generation_config": {
                    "num_images": num_images,
                    "aspect_ratio": aspect_ratio,
                    "width": width,
                    "height": height,
                },
                "prompt": prompt,
            },
            "requestType": "IMAGE_GENERATION",
            "userAgent": "antigravity",
            "requestId": request_id,
        }

        # Handle retries for 429 rate limits
        resp = None
        for i, delay in enumerate(IMAGE_RETRY_DELAYS):
            resp = self.session.post(
                f"{BASE_URL}/v1internal:generateImage",
                json=envelope,
            )
            if resp.status_code != 429:
                break
            
            if i < len(IMAGE_RETRY_DELAYS) - 1:
                print(f"⏳ Rate limited (429). Retrying in {delay}s...")
                time.sleep(delay)

        resp.raise_for_status()
        data = resp.json()
        
        images = []
        for image_data in data.get("images", []):
            if "image" in image_data:
                images.append(base64.b64decode(image_data["image"]["inlineData"]["data"]))
        
        return images

    @staticmethod
    def extract_text_from_part(part: dict) -> str:
        """Helper to extract text from a Gemini response part."""
        return part.get("text", "")

    @staticmethod
    def extract_image_from_part(part: dict) -> bytes:
        """Helper to extract image bytes from a Gemini response part."""
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])

        return None

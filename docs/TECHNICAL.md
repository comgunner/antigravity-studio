# antigravity-studio

Google Antigravity (Cloud Code Assist) client in pure Python — text chat + image generation + agentic tasks.

Enhanced with strategies from [Antigravity-Manager](https://github.com/lbjlaq/Antigravity-Manager) Rust project.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Endpoint Fallback Chain](#endpoint-fallback-chain)
- [Project ID Resolution](#project-id-resolution)
- [Free-Tier Image Generation](#free-tier-image-generation)
- [Rate Limit & Cooldown](#rate-limit--cooldown)
- [Multi-Account Strategy](#multi-account-strategy)
- [API Request Structure](#api-request-structure)
- [File Structure](#file-structure)
- [Troubleshooting](#troubleshooting)
- [Changelog](#changelog)

---

## Quick Start

### Install

```bash
pip install -r requirements.txt
```

### Login

```bash
python3 antigravity_cli.py login
```

Opens browser for OAuth. Credentials saved to `./auth.json`.

### Chat

```bash
python3 antigravity_cli.py chat "What is Python?"
python3 antigravity_cli.py chat "Hola" --model gemini-3-flash
```

### Generate Images

```bash
python3 antigravity_cli.py img "A cute cat wearing sunglasses" -o cat.png
python3 antigravity_cli.py img "Cyberpunk city" --cooldown 600  # 10 min cooldown
```

### List Models

```bash
python3 antigravity_cli.py models
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        antigravity-studio                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  antigravity_cli.py                                              │
│  ├── cmd_login     → Browser/device OAuth2 PKCE                 │
│  ├── cmd_chat      → Text queries with failover                 │
│  ├── cmd_img       → Image generation + cooldown + summary      │
│  └── cmd_accounts  → Multi-account management                    │
│                                                                  │
│  antigravity_auth.py                                             │
│  ├── login_browser()     → OAuth2 PKCE via local callback        │
│  ├── login_device_code() → Headless device code flow             │
│  ├── save_auth() / load_auth() → auth.json read/write           │
│  ├── extract_email_from_id_token() → Parse JWT for email         │
│  └── Multi-account: list, add, switch, remove                   │
│                                                                  │
│  antigravity_client.py                                           │
│  ├── AntigravityClient                                           │
│  │   ├── fetch_project_id() → 3-tier endpoint fallback          │
│  │   ├── list_models()    → Available models per account        │
│  │   ├── chat()           → Text with safety OFF               │
│  │   └── generate_image() → Image with safety OFF              │
│  └── Endpoint chain: Sandbox → Daily → Prod                     │
│                                                                  │
│  auth.json                                                       │
│  └── credentials → google-antigravity → {token, project, email} │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Endpoint Fallback Chain

This is the **most critical difference** from the original port.

### Original (broken for free-tier)

```python
BASE_URL = "https://cloudcode-pa.googleapis.com"  # Prod only
```

Single endpoint. If Prod is rate-limited or unreachable → **429/500**.

### Enhanced (from Antigravity-Manager)

```python
BASE_URL_FALLBACKS = [
    "https://daily-cloudcode-pa.sandbox.googleapis.com",  # Priority 1: Sandbox (less traffic)
    "https://daily-cloudcode-pa.googleapis.com",          # Priority 2: Daily (moderate traffic)
    "https://cloudcode-pa.googleapis.com",                 # Priority 3: Prod (most traffic)
]
```

**How it works:** Every API call tries endpoints in order. If endpoint 1 returns 429/500/503,
it falls back to endpoint 2, then endpoint 3. This gives **3× more chances** to connect.

**Why Sandbox is better:** Less rate-limited because fewer clients use it. The Antigravity-Manager
Rust project discovered this chain in `src-tauri/src/proxy/upstream/client.rs`.

**Applied to:** `loadCodeAssist`, `fetchAvailableModels`, `generateContent` (chat + image).

---

## Project ID Resolution

### The Problem

Google Antigravity requires a `project_id` in every API request. Without one, image generation
returns **500 Internal Server Error**.

**Paid accounts** (Pro/Enterprise): `loadCodeAssist` returns `cloudaicompanionProject: "instant-anthem-5bxbf"` ✅

**Free-tier accounts**: `loadCodeAssist` returns tiers but **NO** `cloudaicompanionProject` ❌

### Original Behavior (broken)

```python
project_id = data.get("cloudaicompanionProject")
if not project_id:
    return ""  # Empty → 500 on image generation
```

### Enhanced Behavior (from Antigravity-Manager)

```python
FALLBACK_PROJECT_ID = "bamboo-precept-lgxtn"  # Shared free-tier project

# Try all 3 endpoints
for base_url in BASE_URL_FALLBACKS:
    resp = post(f"{base_url}/v1internal:loadCodeAssist", ...)
    if resp.ok and resp.json().get("cloudaicompanionProject"):
        return resp.json()["cloudaicompanionProject"]

# All endpoints exhausted → use fallback
return FALLBACK_PROJECT_ID
```

This `bamboo-precept-lgxtn` project appears to be Google's default shared project for
free-tier Antigravity users. The Rust project uses it in 4+ locations as a fallback.

### loadCodeAssist Request (updated)

```python
# Old:
{"metadata": {"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}}

# New (from Antigravity-Manager):
{"metadata": {"ideType": "ANTIGRAVITY"}}
```

The `ANTIGRAVITY` ideType is the newer, correct identifier for Google's API.

---

## Free-Tier Image Generation

### Why Free Accounts Get 500

| Scenario | Response | Cause |
|----------|----------|-------|
| Empty `project_id` | 500 | Server can't route request |
| Invalid `project_id` | 403 | "Permission denied on resource project" |
| No Gemini API enabled | 403 | "Gemini for Google Cloud API has not been used" |
| Rate limited | 429 | ~1 image per 5-10 minutes per account |

### Solution

1. **Fallback project_id** (`bamboo-precept-lgxtn`) — prevents 500 from empty project
2. **3-tier endpoint chain** — Sandbox may accept when Prod rejects
3. **Safety settings OFF** — reduces server-side filtering overhead

### Confirmed Limitations

- The cooldown is **per Google account**, NOT per project or endpoint
- Changing `project_id` does NOT bypass rate limits
- Free-tier accounts share the same cooldown as paid accounts
- Image generation allows **~1 image every 5-10 minutes** regardless of tier

---

## Rate Limit & Cooldown

### API Rate Limits (confirmed by real testing)

| Operation | Limit | Cooldown |
|-----------|-------|----------|
| Chat | ~6-10 req/min | ~2-5 seconds between requests |
| Image generation | ~1-2 per 10 min | 5-10 minutes between images |

### Cooldown Behavior

After every **successful** image generation:

```
✓ Image saved: cat.png (942,384 bytes)
⏱ Generation time: 12s

⏳ Cooldown: waiting 300s before next generation (anti-ban protection)...
✓ Cooldown complete.
```

**Default cooldown:** 300 seconds (5 minutes) — based on real testing showing 5-10 min actual cooldown.

**Customize:**

```bash
python3 antigravity_cli.py img "A cat" -o cat.png --cooldown 600   # 10 min
python3 antigravity_cli.py img "A cat" -o cat.png --cooldown 0      # No cooldown (risky)
```

### What Happens on 429

```
⚠ Account 'Default' is on cooldown, trying next account...
```

**Fail-fast:** No delays on 429/500 — immediately tries the next account (if configured).

---

## Multi-Account Strategy

### Why Multiple Accounts?

Since the cooldown is **per account**, adding multiple Google accounts allows generating
images in parallel — when Account A hits 429, the CLI automatically tries Account B.

### Setup

```bash
# Add account slot
python3 antigravity_cli.py accounts add work --label "Work Account"

# Login with different Google account
python3 antigravity_cli.py login --account work

# List all accounts
python3 antigravity_cli.py accounts

# Generate — auto-failover if active account is on cooldown
python3 antigravity_cli.py img "A sunset" -o sunset.png
```

### Auto-Failover Flow

```
Account A (active) → 429 → ⚠ cooldown, try next
Account B          → 429 → ⚠ cooldown, try next
Account C          → ✅ generates image → 5 min cooldown
```

**No delays between account attempts.** The CLI tries each account instantly.

### Account Display

```bash
python3 antigravity_cli.py accounts
```

Shows email, project_id, token status, and auth state for each account.

---

## API Request Structure

### Image Generation Request

```json
{
    "project": "instant-anthem-5bxbf",
    "model": "gemini-3.1-flash-image",
    "request": {
        "contents": [
            {"role": "user", "parts": [{"text": "A cute cat wearing sunglasses"}]}
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE"]
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "OFF"}
        ]
    },
    "requestType": "CHAT",
    "userAgent": "antigravity",
    "requestId": "py-img-1712500000000-abc123def"
}
```

**Safety settings** are set to `"OFF"` to prevent server-side content filtering blocks.
From Antigravity-Manager: `src-tauri/src/proxy/handlers/openai.rs`.

### Chat Request

Same structure as image, but:
- `model`: `gemini-3-flash`, `gemini-3-pro-high`, etc.
- `generationConfig`: includes `maxOutputTokens` and `temperature`
- `safetySettings`: same (all OFF)

---

## File Structure

```
antigravity-studio/
├── antigravity_auth.py       # OAuth2 PKCE, device code, token refresh, email extraction
├── antigravity_client.py     # API client: chat, image, models, project resolution
├── antigravity_cli.py        # CLI commands: login, chat, img, accounts
├── auth.json                 # Credentials (commit-safe, tokens expire in 1 hour)
├── requirements.txt          # Only: requests>=2.31.0
├── test_auth.py              # 27 auth tests
├── test_client.py            # 10 client tests
└── TECHNICAL.md              # This document
```

### Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `BASE_URL_FALLBACKS` | 3 URLs | Endpoint chain: Sandbox → Daily → Prod |
| `FALLBACK_PROJECT_ID` | `bamboo-precept-lgxtn` | Free-tier shared project |
| `IMAGE_RETRY_DELAYS` | `[30, 60, 120, 300, 600]` | Backoff for non-429 errors |
| `CHAT_RETRY_DELAYS` | `[5, 15, 30]` | Backoff for chat 429 |
| `SAFETY_SETTINGS` | 5 categories OFF | Prevent content filtering blocks |
| Default cooldown | 300s | Anti-ban protection after image generation |

---

## Troubleshooting

### 429 Rate Limited

**Cause:** Too many requests. Image cooldown is 5-10 minutes per account.

**Solution:**
- Wait 5-10 minutes and try again
- Add a second Google account for failover
- The CLI auto-tries other accounts if one is on cooldown

### 500 Internal Server Error

**Cause:** `project_id` is empty or invalid.

**Solution:**
- Re-login: `python3 antigravity_cli.py login`
- The fallback project (`bamboo-precept-lgxtn`) should handle free-tier accounts
- If still failing, the account may not have Antigravity access at all

### 403 Permission Denied

**Cause:** The Google account hasn't accepted the Antigravity terms.

**Solution:**
- Visit https://codeassist.google.com/upgrade and accept the terms
- Then login again: `python3 antigravity_cli.py login`

### Token Expired

**Symptom:** All requests return 401.

**Solution:**
```bash
python3 antigravity_cli.py refresh   # Auto-refresh access token
python3 antigravity_cli.py login     # If refresh token expired (~7 days)
```

### Email Shows "unknown"

The email is extracted from the `id_token` (JWT) returned during OAuth login.
If it shows "unknown", re-login: `python3 antigravity_cli.py login`

---

## Changelog

### v2.0 — Antigravity-Manager Enhancements

**Endpoint Fallback Chain**
- Added 3-tier endpoint fallback: Sandbox → Daily → Prod
- Applied to: `loadCodeAssist`, `fetchAvailableModels`, `chat`, `generate_image`
- Source: Antigravity-Manager `src-tauri/src/proxy/upstream/client.rs`

**Project ID Resolution**
- Added `FALLBACK_PROJECT_ID = "bamboo-precept-lgxtn"` for free-tier accounts
- Updated `loadCodeAssist` to use `ideType: "ANTIGRAVITY"` (was `IDE_UNSPECIFIED`)
- Source: Antigravity-Manager `src-tauri/src/proxy/project_resolver.rs`

**Safety Settings**
- Added 5 safety categories all set to `"OFF"`
- Applied to both chat and image generation requests
- Source: Antigravity-Manager `src-tauri/src/proxy/handlers/openai.rs`

**Email Extraction**
- Parse `id_token` (JWT) to extract user email during login
- Works for both browser OAuth and device code flow

**Rate Limit Improvements**
- Fail-fast on 429/500 — no delays, immediate next-account failover
- Mandatory cooldown (300s default) after successful image generation
- Attempt summary table showing timing for each account tried

### v1.0 — Initial Port

- OAuth2 PKCE login (browser + device code)
- Token refresh
- Chat/text queries
- Image generation with reference images
- Multi-account support
- CLI interface

---

## References

- [Antigravity-Manager (Rust)](https://github.com/lbjlaq/Antigravity-Manager) — Enhanced strategies
- [Google Cloud Code Assist API](https://cloud.google.com/code-assist) — Official API docs

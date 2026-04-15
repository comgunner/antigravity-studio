# Error 429 in Image Generation — Antigravity

**Date:** 2026-04-14
**Endpoint:** `https://cloudcode-pa.googleapis.com/v1/internal/models/{model}:generateContent`
**Confirmed working model:** `gemini-3.1-flash-image`

---

## 1. Root Cause

The 429 error in Antigravity has **two distinct causes** that are frequently confused:

### Cause A: Per-User Rate Limit (Image Cooldown)
- **Limit:** ~1-2 images every **5-10 minutes**
- **Message:** `429 Too Many Requests`
- **Scope:** Individual per Google account
- **Solution:** **Multi-account rotation.** Since version 2.1, `antigravity-studio` implements a per-account cooldown system that automatically skips blocked accounts and rotates to the next available one.

### Cause B: Server-Side Capacity Exhaustion (Global)
- **Cause:** Server capacity exhaustion on `cloudcode-pa.googleapis.com`
- **Message:** `MODEL_CAPACITY_EXHAUSTED` / `RESOURCE_EXHAUSTED` / `rateLimitExceeded`
- **Scope:** Global — affects ALL users (Free, Pro, Enterprise, Ultra)
- **No fixed cooldown** — depends on global server load
- **No reliable workaround** — changing model or project ID does not help

---

## 2. What Does NOT Work

| Strategy | Result | Why |
|----------|--------|-----|
| Change model (`gemini-3-flash-image`, `gemini-2.5-flash-image`, etc.) | ❌ 404 or same 429 | Only `gemini-3.1-flash-image` exists in Antigravity |
| Change project ID | ❌ No effect | Rate limit is per Google account, not per project |
| Custom headers | ❌ No effect | Server validates OAuth session |
| Aggressive retries | ❌ Makes it worse | Can cause temporary IP/account bans |
| Use proxies | ❌ Dangerous | Google detects and bans accounts using proxies |

---

## 3. Community-Implemented Solutions

### 3.1 Antigravity-Manager (lbjlaq/Antigravity-Manager)

Rust project implementing the most advanced strategies to avoid 429:

| Strategy | Description | Implemented in this Project (v2.1) |
|----------|-------------|----------------------|
| **Auto-Failover** | On 429, automatically retry with next available account | ✅ Yes |
| **Circuit Breaker per Account** | 429 blocks only that account, others keep working | ✅ Yes (SQLite persistence) |
| **Health Score Routing** | Accounts with 429 get lower priority until recovered | ✅ Yes (Smart skipping) |
| **Mandatory Cooldown** | Anti-ban wait after successful generation | ✅ Yes (300s default) |
| **Endpoint Fallback** | `Sandbox → Daily → Prod` automatic fallback chain | ✅ Yes |
| **Strict Retry-After** | Respects server's `Retry-After` header | ✅ Yes |

### 3.2 Gemini CLI (google-gemini/gemini-cli)

- **Root cause:** Gemini CLI internal routing forces tool calls to `gemini-3-flash-preview` regardless of selected model. When that model is saturated, the entire session fails.
- **Status:** No official fix. Google acknowledges the issue but no timeline for resolution.
- **Reported workaround:** Using **AI Studio web** with the same account works normally.

---

## 4. Current Best Practices

### 4.1 Recommended Cooldowns (per account)

- **On Success:** 300 seconds (5 minutes) anti-ban wait.
- **On 429:** 3600 seconds (1 hour) penalty to allow full quota reset.

### 4.2 Multi-Account Rotation

```bash
# Add multiple accounts to multiply your capacity
python3 antigravity_cli.py accounts add work
python3 antigravity_cli.py login --account work

# The CLI will automatically rotate through all configured accounts
python3 antigravity_cli.py img "A beautiful landscape"
```

### 4.3 Intelligent Fallback

If all accounts are on cooldown, `antigravity-studio` will identify the account that becomes available soonest. If the wait is less than 5 minutes, it will offer to wait automatically.

---

## 5. Current Status of Image Models in Antigravity

| Model | Exists | Works | Cooldown |
|-------|--------|-------|----------|
| `gemini-3.1-flash-image` | ✅ | ✅ | 5-10 min |
| `gemini-3-flash-image` | ❌ 404 | — | — |
| `gemini-2.5-flash-image` | ❌ 404 | — | — |

---

## 6. References

| Source | URL |
|--------|-----|
| Antigravity-Manager | https://github.com/lbjlaq/Antigravity-Manager |
| Gemini CLI Issue #22545 | https://github.com/google-gemini/gemini-cli/issues/22545 |
| antigravity-studio Docs | `./docs/TECHNICAL.md` |

---

*error_429.md — 2026-04-14*
*Last verification: gemini-3.1-flash-image is the only functional image model in Antigravity*

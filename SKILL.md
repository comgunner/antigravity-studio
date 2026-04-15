---
name: antigravity-studio
description: >
  Google Antigravity (Cloud Code Assist) client in pure Python.
  Capabilities: multi-model text chat, high-quality image generation (with
  reference images), multi-asset technical analysis (Crypto + Forex + Metals +
  Indices), and multi-account auto-failover. Features 3-tier endpoint fallback
  (Sandbox → Daily → Prod), safety settings OFF, mandatory cooldown management,
  and OAuth2 PKCE authentication.
---

# Antigravity Studio Skill

## Purpose

Full-stack AI assistant for: (1) market technical analysis across Crypto,
Forex, Metals, and Indices; (2) high-quality image generation with reference
images and multi-account failover; (3) agentic chat for code analysis,
debugging, and autonomous tasks.

---

## Setup & Installation

```bash
# Install as a picoclaw-agents Skill
cd ~/.picoclaw/workspace/skills
git clone https://github.com/comgunner/antigravity-studio
cd antigravity-studio
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Authenticate (OAuth browser)
python3 antigravity_cli.py login

# Or headless / SSH / Termux
python3 antigravity_cli.py login --device
```

---

## Triggers & Capabilities

### 1. Technical Analysis (Market Summaries)

**When to use:** user asks for price levels, trend sentiment, EMAs, key
support/resistance, or a market overview.

**Triggers:** "BTC summary", "Gold analysis", "XAU technicals", "Nasdaq
sentiment", "EMA 200 for SOL", "resumen técnico de ETH".

**Command:**
```bash
python3 antigravity_cli.py --resume [symbol] --tf [15m|1h|4h|1d]
```

**Supported Assets:**

| Category | Symbols |
|----------|---------|
| Crypto (Binance) | `btc`, `eth`, `sol`, `ada`, `bnb`, etc. |
| Metals | `xau` (Gold), `xag` (Silver) |
| Forex | `eurusd`, `gbpusd`, `jpymxn`, `mxn` |
| Indices | `gspc` (S&P 500), `ixic` (Nasdaq), `dxy` (Dollar Index) |
| Commodities | `cl` (Crude Oil WTI) |

**Examples:**
```bash
python3 antigravity_cli.py --resume btc --tf 4h      # BTC 4h
python3 antigravity_cli.py --resume xau --tf 1h      # Gold 1h
python3 antigravity_cli.py --resume ixic --tf 1h     # Nasdaq 1h
python3 antigravity_cli.py --resume gspc --tf 1d     # S&P 500 daily
python3 antigravity_cli.py --resume eurusd --tf 1h   # EUR/USD 1h
python3 antigravity_cli.py --resume cl --tf 15m      # Crude Oil 15m
```

**Output includes:** EMAs (3, 9, 21, 50, 200), AI sentiment (Bullish/Bearish),
key support/resistance levels, saved to `summary_[symbol]_[tf].json`.

---

### 2. Image Generation

**When to use:** user wants to create images, banners, logos, social media
assets, or stylized visuals; especially when they say "generate", "create",
"design", "imagen".

**Triggers:** "Generate an image of...", "Create a banner for...", "Design a
logo...", "Using this reference image, create...", "Genera una imagen de...".

**Command:**
```bash
python3 antigravity_cli.py img "[prompt]" \
  -o [output.png] \
  --aspect-ratio [1:1|16:9|9:16|4:5] \
  --model gemini-3.1-flash-image \
  -r [reference.png]   # up to 10 reference images
```

**Aspect Ratios:**

| Ratio | Use Case |
|-------|----------|
| `1:1` | Square — Instagram, general purpose (default) |
| `16:9` | Landscape — YouTube thumbnails, banners, cinematic |
| `9:16` | Portrait — Stories, vertical mobile |
| `4:5` | Social — Facebook/Instagram feed |

**JSON Prompt Format** (for themed generation with reference):
```bash
python3 antigravity_cli.py img '{
    "id": 1,
    "theme": "Python Branding",
    "prompt": "A promotional graphic with a dark high-tech background..."
}' -r ./logo/logo.png -o output.png
```

| JSON Field | Required | Description |
|------------|----------|-------------|
| `prompt` | ✅ | Image description |
| `theme` | ❌ | Prepended as `"Theme: {theme}. {prompt}"` |
| `id` | ❌ | Internal identifier |

**Rate Limits & Cooldown:**

| Limit | Value |
|-------|-------|
| Images per 10 minutes | ~1–2 |
| Mandatory cooldown | 300s (5 min) default after success |
| Custom cooldown | `--cooldown 600` (10 min) or `--cooldown 0` (risky) |
| Auto-retry backoff | 30s → 60s → 120s → 300s → 600s |

**Multi-Account Failover (automatic):**
```
Account A (active) → 429 → ⚠ skip, try next (0s wait)
Account B          → 429 → ⚠ skip, try next (0s wait)
Account C          → ✅  → image saved, cooldown starts
```

**Examples:**
```bash
# Simple 1:1
python3 antigravity_cli.py img "A cute cat wearing sunglasses" -o cat.png

# Cinematic 16:9
python3 antigravity_cli.py img "Cyberpunk city at night" --aspect-ratio 16:9 -o city.png

# Portrait 9:16
python3 antigravity_cli.py img "Portrait of a samurai warrior" --aspect-ratio 9:16 -o samurai.png

# With logo reference
python3 antigravity_cli.py img "A banner with the logo" -r ./logo/logo.png -o banner.png

# With JSON theme + reference
python3 antigravity_cli.py img '{"theme": "Matrix", "prompt": "Neo in the rain of green code"}' \
  -r ./logo/logo.png --aspect-ratio 4:5 -o neo_banner.png
```

---

### 3. Agentic Chat & Reasoning

**When to use:** complex code analysis, bug debugging, research, autonomous
multi-step tasks, or any reasoning-heavy conversation.

**Triggers:** "Analyze this code...", "Debug this error...", "Research how X
works...", "Autonomous task: ...", "Analiza este código...", "Depura este
error...".

**Command:**
```bash
python3 antigravity_cli.py chat "[prompt]" \
  --model [model] \
  --max-tokens [256-8192] \
  --temperature [0.0-1.0]
```

**Available Models:**

| Model ID | Type | Best For |
|----------|------|----------|
| `gemini-3-flash` | Chat | Fast text chat (default) |
| `gemini-3-flash-agent` | Agentic | Code execution, tool use, multi-step tasks |
| `gemini-3-pro-high` | Chat | High-quality text, complex reasoning |
| `gemini-3-pro-low` | Chat | Good quality, faster |
| `gemini-3.1-flash-image` | Image | Image generation (use with `img` cmd) |
| `gemini-2.5-pro` | Chat | Gemini 2.5 Pro |
| `gemini-2.5-flash` | Chat | Fast and lightweight |
| `claude-sonnet-4-6` | Chat | Claude via Antigravity |
| `claude-opus-4-6-thinking` | Chat | Claude Opus with extended thinking |
| `gpt-oss-120b-medium` | Chat | GPT-OSS 120B |

> Run `python3 antigravity_cli.py models` to see the current live list.

**Examples:**
```bash
# Simple chat
python3 antigravity_cli.py chat "What is the capital of France?"

# Agentic code analysis
python3 antigravity_cli.py chat "Analyze this Python code and suggest improvements" \
  --model gemini-3-flash-agent

# Complex reasoning with more tokens
python3 antigravity_cli.py chat "Explain quantum computing" \
  --model gemini-3-pro-high --max-tokens 4096

# Debug a traceback
python3 antigravity_cli.py chat "Debug this error: IndexError: list index out of range" \
  --model gemini-3-flash-agent --max-tokens 8192
```

---

### 4. Account & Identity Management

**When to use:** adding accounts to bypass rate limits, switching between
identities, or listing configured credentials.

**Triggers:** "Add account", "List my accounts", "Switch to work account",
"Agregar una cuenta nueva".

**Commands:**
```bash
# List all configured accounts (shows email, auth status, project ID)
python3 antigravity_cli.py accounts

# Add a new account slot
python3 antigravity_cli.py accounts add work --label "Work Account"

# Authenticate the new account slot
python3 antigravity_cli.py login --account work

# Switch active account
python3 antigravity_cli.py accounts switch work

# Remove an account
python3 antigravity_cli.py accounts remove work
```

**Full workflow for a second account:**
```bash
python3 antigravity_cli.py accounts add work --label "Work Account"
python3 antigravity_cli.py login --account work
python3 antigravity_cli.py accounts                   # verify
python3 antigravity_cli.py accounts switch work
python3 antigravity_cli.py img "A cat" -o cat.png     # uses work account
```

---

### 5. Auth Maintenance

```bash
# Refresh expired access token (~1 hour)
python3 antigravity_cli.py refresh

# Re-login when refresh token expires (~7 days)
python3 antigravity_cli.py login
```

| Token | Validity | Auto-refresh |
|-------|----------|--------------|
| Access token | ~1 hour | ✅ Automatic on every API call |
| Refresh token | ~7 days | ❌ Manual `login` required |

---

## Rules

- **Symbol flexibility:** `btc`, `BTCUSDT`, `xau`, `GOLD` are all valid for `--resume`.
- **Indicators:** Analysis always includes EMAs (3, 9, 21, 50, 200).
- **Reference images:** Sent as base64. Supported: PNG, JPEG, WebP (≤ 5MB each). First image has highest semantic weight.
- **Security:** Never log or commit `auth.json`. It contains refresh tokens.
- **Model selection:** Use `gemini-3-flash-agent` for agentic tasks; `gemini-3-flash` for simple chat.
- **Language:** Technical analysis output and chat responses are in English by default.

---

## Quick Reference Examples

```bash
# --- TECHNICAL ANALYSIS ---
python3 antigravity_cli.py --resume btc --tf 4h
python3 antigravity_cli.py --resume xau --tf 1h
python3 antigravity_cli.py --resume gspc --tf 1d

# --- IMAGE GENERATION ---
python3 antigravity_cli.py img "Cyberpunk city at night" --aspect-ratio 16:9 -o city.png
python3 antigravity_cli.py img "Create a banner with this logo" -r ./logo/logo.png -o banner.png
python3 antigravity_cli.py img "A cat" -o cat.png --cooldown 600

# --- CHAT ---
python3 antigravity_cli.py chat "Explain quantum computing" --model gemini-3-pro-high
python3 antigravity_cli.py chat "Debug this Python traceback..." --model gemini-3-flash-agent

# --- ACCOUNTS ---
python3 antigravity_cli.py accounts
python3 antigravity_cli.py accounts add work && python3 antigravity_cli.py login --account work

# --- MAINTENANCE ---
python3 antigravity_cli.py models
python3 antigravity_cli.py refresh
```

# Image Generation Flow

Step-by-step walkthrough of how `antigravity_cli.py img` generates an image.

---

## Example Output

```
$ python3 antigravity_cli.py img "A cute dog wearing sunglasses" -o cat.png
Model: gemini-3.1-flash-image
Prompt: A cute dog wearing sunglasses
Generating image...
⚠ Account 'Default' is on cooldown, trying next account...
✓ Generated using account: work
✓ Image saved: cat.png (887,449 bytes)
⏱ Generation time: 39s

⏳ Cooldown: waiting 300s before next generation (anti-ban protection)...
✓ Cooldown complete.

============================================================
📊 ATTEMPT SUMMARY
============================================================
Account              Status             Time     Details
────────────────────────────────────────────────────────────
  Default            429 COOLDOWN       0s
  work               SUCCESS           39s (887,449 bytes)
────────────────────────────────────────────────────────────
  ✅ SUCCESS | Total time: 342s | Attempts: 2
============================================================
```

---

## Flow Diagram

```
User runs: python3 antigravity_cli.py img "prompt" -o output.png
│
├─► 1. PARSE ARGS
│    ├── prompt:     "A cute dog wearing sunglasses"
│    ├── model:      gemini-3.1-flash-image (default)
│    ├── output:     cat.png
│    ├── cooldown:   300s (default, configurable with --cooldown)
│    └── aspect:     1:1 (default)
│
├─► 2. LOAD ACCOUNTS
│    ├── Read auth.json → discover all credentials
│    ├── Read antigravity_config.json → get account names
│    ├── Order: active account first, then others
│    └── Example: [Default(active), work, work2]
│
├─► 3. TRY ACCOUNTS (fail-fast loop)
│    │
│    ├─► Account: Default (active)
│    │   ├── Get valid token → refresh if expired
│    │   ├── Create AntigravityClient(token, project_id)
│    │   │
│    │   ├──► generate_image()
│    │   │   ├── Parse prompt (supports JSON with "prompt" field)
│    │   │   ├── Strip model prefixes
│    │   │   ├── Build parts: [{"text": "A cute dog..."}]
│    │   │   ├── Build envelope:
│    │   │   │   {
│    │   │   │     "project": "instant-anthem-5bxbf",
│    │   │   │     "model": "gemini-3.1-flash-image",
│    │   │   │     "request": {
│    │   │   │       "contents": [{"role":"user","parts":[...]}],
│    │   │   │       "generationConfig": {"responseModalities":["IMAGE"]},
│    │   │   │       "safetySettings": [ALL "OFF"]
│    │   │   │     },
│    │   │   │     "requestType": "CHAT",
│    │   │   │     "requestId": "py-img-..."
│    │   │   │   }
│    │   │   │
│    │   │   ├──► ENDPOINT FALLBACK CHAIN
│    │   │   │   ├── Try: daily-cloudcode-pa.sandbox.googleapis.com
│    │   │   │   │   └── Status: 429 → try next
│    │   │   │   ├── Try: daily-cloudcode-pa.googleapis.com
│    │   │   │   │   └── Status: 429 → try next
│    │   │   │   └── Try: cloudcode-pa.googleapis.com
│    │   │   │       └── Status: 429 → all endpoints exhausted
│    │   │   │
│    │   │   └── Result: HTTPError 429 → FAIL FAST (0s wait)
│    │   │
│    │   └── CLI catches 429 → "⚠ Account 'Default' is on cooldown, trying next..."
│    │
│    ├─► Account: work
│    │   ├── Get valid token
│    │   ├── Create AntigravityClient(token, project_id)
│    │   │
│    │   ├──► generate_image()
│    │   │   ├── Same envelope as above
│    │   │   │
│    │   │   ├──► ENDPOINT FALLBACK CHAIN
│    │   │   │   ├── Try: daily-cloudcode-pa.sandbox.googleapis.com
│    │   │   │   │   └── Status: 200 ✅ SUCCESS
│    │   │   │   └── (no need to try Daily/Prod)
│    │   │   │
│    │   │   ├── Extract base64 image from response
│    │   │   │   └── candidates[0].content.parts[0].inlineData.data
│    │   │   └── Decode base64 → return bytes (887,449 bytes)
│    │   │
│    │   └── SUCCESS!
│    │
│    └─► (Remaining accounts skipped — we already got the image)
│
├─► 4. SAVE IMAGE
│    ├── Write bytes to: cat.png
│    ├── Print: "✓ Image saved: cat.png (887,449 bytes)"
│    └── Print: "⏱ Generation time: 39s"
│
├─► 5. MANDATORY COOLDOWN
│    ├── Wait 300s (5 min) — anti-ban protection
│    ├── Configurable: --cooldown 600 (10 min), --cooldown 0 (none)
│    └── Print: "⏳ Cooldown: waiting 300s... ✓ Cooldown complete."
│
├─► 6. ATTEMPT SUMMARY
│    ├── Print table with all attempts:
│    │   - Account name
│    │   - Status (429 COOLDOWN / SUCCESS / 500 ERROR / ERROR)
│    │   - Time spent
│    │   - Details (file size or error message)
│    └── Print: "✅ SUCCESS | Total time: 342s | Attempts: 2"
│
└─► 7. EXIT
     └── Process ends successfully (exit 0)
```

---

## Endpoint Fallback Chain (Detail)

Every API call (chat or image) tries 3 endpoints **in order**:

```
Priority 1: https://daily-cloudcode-pa.sandbox.googleapis.com/v1internal
Priority 2: https://daily-cloudcode-pa.googleapis.com/v1internal
Priority 3: https://cloudcode-pa.googleapis.com/v1internal
```

**Behavior:**
- If endpoint returns **200** → use it, stop trying
- If endpoint returns **429/500/503** → try next endpoint
- If endpoint returns **other error** (400, 401, 403, etc.) → stop and raise error

**Why this matters:**
- **Sandbox** has less traffic and less rate limiting
- If all 3 endpoints return 429 → account is fully on cooldown
- The fallback gives **3× more chances** to connect per account

---

## Account Failover (Detail)

```
For each account (active first):
    │
    ├── Get valid token
    │   └── If expired → auto-refresh
    │   └── If no refresh token → prompt login
    │
    ├── Create client
    │
    ├── Try generate_image()
    │   │
    │   ├── Try endpoint 1 (Sandbox)
    │   │   └── 429 → try endpoint 2
    │   ├── Try endpoint 2 (Daily)
    │   │   └── 429 → try endpoint 3
    │   ├── Try endpoint 3 (Prod)
    │   │   └── 429 → raise HTTPError 429
    │   │
    │   └── Result: 429 error
    │
    ├── CLI catches 429 → "trying next account"
    │   └── NO DELAY — instant failover
    │
    └── Next account → repeat...
```

**Key difference from old behavior:**

| Old | New |
|-----|-----|
| 30s wait on first 429 | **0s wait** — instant next account |
| Only Prod endpoint | **3 endpoints** per account |
| Single account | **Auto-try all accounts** |
| No timing info | **Summary table** with timing |

---

## Cooldown Logic

### After SUCCESSFUL generation

```
Image generated → Save file → Start cooldown timer → Wait → Print summary → Exit
```

**Purpose:** Prevent ban from rapid successive image requests.

**Default:** 300 seconds (5 minutes) — based on real testing showing 5-10 min actual API cooldown.

**Customize:**
```bash
--cooldown 600   # 10 minutes (safer)
--cooldown 120   # 2 minutes (faster, riskier)
--cooldown 0     # No cooldown (high ban risk)
```

### On 429 (rate limited)

```
429 received → Log "429 COOLDOWN" → Next account → NO DELAY
```

**No waiting** between account attempts. The CLI moves to the next account instantly.

### All accounts on cooldown

```
All accounts tried → All returned 429 → Print summary → Exit with error
```

```
❌ All accounts rate limited. Please wait 5-10 minutes and try again.
```

---

## Error Scenarios

### Scenario 1: Account A on cooldown, B succeeds

```
Account A → 429 → ⚠ cooldown
Account B → 200 → ✅ image saved → 5 min cooldown → summary → exit
```

### Scenario 2: All accounts on cooldown

```
Account A → 429 → ⚠ cooldown
Account B → 429 → ⚠ cooldown
Account C → 429 → ⚠ cooldown
All exhausted → ❌ wait 5-10 min
```

### Scenario 3: 500 error (bad project_id)

```
Account A → 500 → ⚠ server error, try next
Account B → 200 → ✅ image saved
```

### Scenario 4: Single account, on cooldown

```
Account A → 429 → all endpoints tried → ❌ wait 5-10 min
```

---

## Timing Breakdown (from example)

```
Total time: 342s
├── Account 'Default': 0s (429 — fail fast, no endpoint responded with 200)
├── Account 'work':    39s (200 — full generation via Sandbox endpoint)
└── Cooldown:         300s (5 min mandatory wait)
                      ─────
                      339s (+ 3s overhead = 342s total)
```

---

## Request Payload (What Gets Sent)

```json
{
    "project": "instant-anthem-5bxbf",
    "model": "gemini-3.1-flash-image",
    "request": {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "A cute dog wearing sunglasses"}
                ]
            }
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

**Headers:**
```
Authorization: Bearer ya29.a0...
Content-Type: application/json
User-Agent: antigravity
X-Goog-Api-Client: google-cloud-sdk vscode_cloudshelleditor/0.1
```

---

## Response Structure (What Comes Back)

```json
{
    "response": {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": "iVBORw0KGgoAAAANSUhEUgAA..."
                            }
                        }
                    ]
                }
            }
        ]
    }
}
```

The `inlineData.data` is **base64-encoded** image bytes. The client decodes and saves to disk.

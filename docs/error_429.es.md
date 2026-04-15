# Error 429 en Generación de Imágenes — Antigravity

**Fecha:** 2026-04-14
**Endpoint:** `https://cloudcode-pa.googleapis.com/v1/internal/models/{model}:generateContent`
**Modelo confirmado funcional:** `gemini-3.1-flash-image`

---

## 1. Causa del Error

El error 429 en Antigravity tiene **dos causas distintas** que se confunden frecuentemente:

### Causa A: Rate Limit por Usuario (Cooldown de Imágenes)
- **Límite:** ~1-2 imágenes cada **5-10 minutos**
- **Mensaje:** `429 Too Many Requests`
- **Scope:** Individual por cuenta de Google
- **Solución:** **Rotación multi-cuenta.** Desde la versión 2.1, `antigravity-studio` implementa un sistema de cooldown por cuenta que salta automáticamente las cuentas bloqueadas y rota a la siguiente disponible.

### Causa B: Server-Side Capacity Exhaustion (Global)
- **Causa:** Agotamiento de capacidad del servidor `cloudcode-pa.googleapis.com`
- **Mensaje:** `MODEL_CAPACITY_EXHAUSTED` / `RESOURCE_EXHAUSTED` / `rateLimitExceeded`
- **Scope:** Global — afecta a TODOS los usuarios (Free, Pro, Enterprise, Ultra)
- **No tiene cooldown fijo** — depende de la carga global del servidor
- **No hay workaround confiable** — ni cambiar modelo ni proyecto ID ayuda

---

## 2. Lo que NO Funciona

| Estrategia | Resultado | Por qué |
|-----------|-----------|---------|
| Cambiar modelo (`gemini-3-flash-image`, `gemini-2.5-flash-image`, etc.) | ❌ 404 o mismo 429 | Solo `gemini-3.1-flash-image` existe en Antigravity |
| Cambiar project ID | ❌ No funciona | El rate limit es por cuenta de Google, no por proyecto |
| Headers custom | ❌ No funciona | El servidor valida la sesión OAuth |
| Reintentar agresivamente | ❌ Empeora | Puede causar bans temporales de IP/cuenta |
| Usar proxies | ❌ Peligroso | Google detecta y banea cuentas con proxies |

---

## 3. Soluciones Implementadas por la Comunidad

### 3.1 Antigravity-Manager (lbjlaq/Antigravity-Manager)

Proyecto Rust que implementa las estrategias más avanzadas para evitar el 429:

| Estrategia | Descripción | Implementado en este Proyecto (v2.1) |
|-----------|-------------|----------------------|
| **Auto-Failover** | En 429, reintenta automáticamente con la siguiente cuenta disponible | ✅ Sí |
| **Circuit Breaker por Cuenta** | El 429 bloquea solo esa cuenta, otras siguen funcionando | ✅ Sí (persistencia SQLite) |
| **Health Score Routing** | Cuentas con 429 reciben menor prioridad hasta recuperarse | ✅ Sí (Salto inteligente) |
| **Cooldown Obligatorio** | Espera anti-ban tras generación exitosa | ✅ Sí (300s por defecto) |
| **Endpoint Fallback** | Cadena de fallback automática `Sandbox → Daily → Prod` | ✅ Sí |
| **Strict Retry-After** | Respeta el header `Retry-After` del servidor | ✅ Sí |

### 3.2 Gemini CLI (google-gemini/gemini-cli)

- **Causa raíz:** El routing interno de Gemini CLI fuerza tool calls a `gemini-3-flash-preview` sin importar el modelo seleccionado. Cuando ese modelo está saturado, toda la sesión falla.
- **Estado:** Sin fix oficial. Google reconoce el problema pero no hay timeline de solución.
- **Workaround reportado:** Usar **AI Studio web** con la misma cuenta funciona normalmente.

---

## 4. Mejores Prácticas Actuales

### 4.1 Cooldowns Recomendados (por cuenta)

- **En Éxito:** 300 segundos (5 minutos) de espera anti-ban.
- **En 429:** 3600 segundos (1 hora) de penalización para permitir reset de cuota.

### 4.2 Rotación Multi-Cuenta

```bash
# Añade múltiples cuentas para multiplicar tu capacidad
python3 antigravity_cli.py accounts add trabajo
python3 antigravity_cli.py login --account trabajo

# El CLI rotará automáticamente entre todas las cuentas configuradas
python3 antigravity_cli.py img "Un paisaje hermoso"
```

### 4.3 Fallback Inteligente

Si todas las cuentas están en cooldown, `antigravity-studio` identificará la cuenta que se libera primero. Si la espera es menor a 5 minutos, ofrecerá esperar automáticamente.

---

## 5. Estado Actual de Modelos de Imagen en Antigravity

| Modelo | Existe | Funciona | Cooldown |
|--------|--------|----------|----------|
| `gemini-3.1-flash-image` | ✅ | ✅ | 5-10 min |
| `gemini-3-flash-image` | ❌ 404 | — | — |
| `gemini-2.5-flash-image` | ❌ 404 | — | — |

---

## 6. Referencias

| Fuente | URL |
|--------|-----|
| Antigravity-Manager | https://github.com/lbjlaq/Antigravity-Manager |
| Gemini CLI Issue #22545 | https://github.com/google-gemini/gemini-cli/issues/22545 |
| antigravity-studio Docs | `./docs/TECHNICAL.es.md` |

---

*error_429.es.md — 2026-04-14*
*Última verificación: gemini-3.1-flash-image es el único modelo de imagen funcional en Antigravity*

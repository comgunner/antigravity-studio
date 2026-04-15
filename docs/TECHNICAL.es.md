# antigravity-studio

Cliente de Google Antigravity (Cloud Code Assist) en Python puro — chat de texto + generación de imágenes + tareas agénticas.

Mejorado con estrategias del proyecto en Rust [Antigravity-Manager](https://github.com/lbjlaq/Antigravity-Manager).

---

## Tabla de Contenidos

- [Inicio Rápido](#inicio-rápido)
- [Arquitectura](#arquitectura)
- [Cadena de Fallback de Endpoints](#cadena-de-fallback-de-endpoints)
- [Resolución de ID de Proyecto](#resolución-de-id-de-proyecto)
- [Generación de Imágenes en Nivel Gratuito](#generación-de-imágenes-en-nivel-gratuito)
- [Rate Limit y Cooldown](#rate-limit-y-cooldown)
- [Estrategia Multi-Cuenta](#estrategia-multi-cuenta)
- [Estructura de la Petición API](#estructura-de-la-petición-api)
- [Estructura de Archivos](#estructura-de-archivos)
- [Solución de Problemas](#solución-de-problemas)
- [Registro de Cambios (Changelog)](#changelog)

---

## Inicio Rápido

### Instalar

```bash
pip install -r requirements.txt
```

### Login

```bash
python3 antigravity_cli.py login
```

Abre el navegador para OAuth. Las credenciales se guardan en `./auth.json`.

### Chat

```bash
python3 antigravity_cli.py chat "¿Qué es Python?"
python3 antigravity_cli.py chat "Hola" --model gemini-3-flash
```

### Generar Imágenes

```bash
python3 antigravity_cli.py img "Un gato lindo con gafas de sol" -o gato.png
python3 antigravity_cli.py img "Ciudad cyberpunk" --cooldown 600  # 10 min de cooldown
```

### Listar Modelos

```bash
python3 antigravity_cli.py models
```

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        antigravity-studio                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  antigravity_cli.py                                              │
│  ├── cmd_login     → OAuth2 PKCE por navegador/dispositivo       │
│  ├── cmd_chat      → Consultas de texto con failover             │
│  ├── cmd_img       → Generación de imagen + cooldown + resumen   │
│  └── cmd_accounts  → Gestión multi-cuenta                        │
│                                                                  │
│  antigravity_auth.py                                             │
│  ├── login_browser()     → OAuth2 PKCE vía callback local        │
│  ├── login_device_code() → Flujo de código de dispositivo        │
│  ├── save_auth() / load_auth() → Lectura/escritura de auth.json  │
│  ├── extract_email_from_id_token() → Parsear JWT para el email   │
│  └── Multi-cuenta: listar, añadir, cambiar, eliminar             │
│                                                                  │
│  antigravity_client.py                                           │
│  ├── AntigravityClient                                           │
│  │   ├── fetch_project_id() → Fallback de endpoint en 3 niveles  │
│  │   ├── list_models()    → Modelos disponibles por cuenta       │
│  │   ├── chat()           → Texto con seguridad en OFF           │
│  │   └── generate_image() → Imagen con seguridad en OFF          │
│  └── Cadena de endpoints: Sandbox → Daily → Prod                 │
│                                                                  │
│  auth.json                                                       │
│  └── credentials → google-antigravity → {token, proyecto, email} │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Cadena de Fallback de Endpoints

Esta es la **diferencia más crítica** respecto al port original.

### Original (no funcionaba para el nivel gratuito)

```python
BASE_URL = "https://cloudcode-pa.googleapis.com"  # Solo Prod
```

Endpoint único. Si Prod tiene rate-limit o no está disponible → **429/500**.

### Mejorado (de Antigravity-Manager)

```python
BASE_URL_FALLBACKS = [
    "https://daily-cloudcode-pa.sandbox.googleapis.com",  # Prioridad 1: Sandbox (menos tráfico)
    "https://daily-cloudcode-pa.googleapis.com",          # Prioridad 2: Daily (tráfico moderado)
    "https://cloudcode-pa.googleapis.com",                 # Prioridad 3: Prod (más tráfico)
]
```

**Cómo funciona:** Cada llamada a la API intenta los endpoints en orden. Si el endpoint 1 devuelve 429/500/503,
pasa al endpoint 2, luego al 3. Esto da **3 veces más oportunidades** de conectar.

**Por qué Sandbox es mejor:** Tiene menos rate-limit porque menos clientes lo usan. El proyecto Rust
Antigravity-Manager descubrió esta cadena en `src-tauri/src/proxy/upstream/client.rs`.

**Aplicado a:** `loadCodeAssist`, `fetchAvailableModels`, `generateContent` (chat + imagen).

---

## Resolución de ID de Proyecto

### El Problema

Google Antigravity requiere un `project_id` en cada petición API. Sin él, la generación de imágenes
devuelve un **500 Internal Server Error**.

**Cuentas de pago** (Pro/Enterprise): `loadCodeAssist` devuelve `cloudaicompanionProject: "instant-anthem-5bxbf"` ✅

**Cuentas de nivel gratuito**: `loadCodeAssist` devuelve los niveles pero **NO** el `cloudaicompanionProject` ❌

### Comportamiento Original (roto)

```python
project_id = data.get("cloudaicompanionProject")
if not project_id:
    return ""  # Vacío → 500 en generación de imágenes
```

### Comportamiento Mejorado (de Antigravity-Manager)

```python
FALLBACK_PROJECT_ID = "bamboo-precept-lgxtn"  # Proyecto compartido del nivel gratuito

# Intentar los 3 endpoints
for base_url in BASE_URL_FALLBACKS:
    resp = post(f"{base_url}/v1internal:loadCodeAssist", ...)
    if resp.ok and resp.json().get("cloudaicompanionProject"):
        return resp.json()["cloudaicompanionProject"]

# Todos los endpoints agotados → usar fallback
return FALLBACK_PROJECT_ID
```

Este proyecto `bamboo-precept-lgxtn` parece ser el proyecto compartido por defecto de Google para
usuarios de Antigravity de nivel gratuito. El proyecto Rust lo usa en más de 4 lugares como fallback.

### Petición loadCodeAssist (actualizada)

```python
# Anterior:
{"metadata": {"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}}

# Nueva (de Antigravity-Manager):
{"metadata": {"ideType": "ANTIGRAVITY"}}
```

El ideType `ANTIGRAVITY` es el identificador más reciente y correcto para la API de Google.

---

## Generación de Imágenes en Nivel Gratuito

### Por qué las cuentas gratuitas reciben un 500

| Escenario | Respuesta | Causa |
|-----------|-----------|-------|
| `project_id` vacío | 500 | El servidor no puede enrutar la petición |
| `project_id` inválido | 403 | "Permission denied on resource project" |
| API de Gemini no habilitada | 403 | "Gemini for Google Cloud API has not been used" |
| Rate limited | 429 | ~1 imagen cada 5-10 minutos por cuenta |

### Solución

1. **ID de proyecto de fallback** (`bamboo-precept-lgxtn`) — evita el 500 por proyecto vacío
2. **Cadena de endpoints en 3 niveles** — Sandbox puede aceptar cuando Prod rechaza
3. **Configuración de seguridad en OFF** — reduce la carga de filtrado del servidor

### Limitaciones Confirmadas

- El cooldown es **por cuenta de Google**, NO por proyecto o endpoint
- Cambiar el `project_id` NO salta los límites de rate limit
- Las cuentas gratuitas comparten el mismo cooldown que las de pago
- La generación de imágenes permite **~1 imagen cada 5-10 minutos** sin importar el nivel

---

## Rate Limit y Cooldown

### Límites de la API (confirmados con pruebas reales)

| Operación | Límite | Cooldown |
|-----------|--------|----------|
| Chat | ~6-10 pet/min | ~2-5 segundos entre peticiones |
| Generación de imágenes | ~1-2 cada 10 min | 5-10 minutos entre imágenes |

### Comportamiento del Cooldown por Cuenta

A diferencia de versiones anteriores, el cooldown ahora se gestiona **individualmente por cuenta**. Esto permite rotar cuentas: si la cuenta A está bloqueada, el sistema intenta automáticamente con la cuenta B.

**Tipos de Cooldown:**
1. **Éxito:** Tras generar una imagen correctamente, la cuenta entra en un cooldown corto (por defecto 300s / 5 min) para evitar detección de baneo.
2. **429 (Rate Limit):** Si la API devuelve un error 429, la cuenta recibe una penalización larga (por defecto 3600s / 1 hora).

### Qué pasa con un 429

```
⚠ La cuenta 'trabajo' está en cooldown (429), penalizando 1h...
⚠ Intentando con la siguiente cuenta disponible...
```

**Fail-fast:** Sin esperas globales — intenta inmediatamente la siguiente cuenta configurada que no esté en cooldown.

---

## Estrategia Multi-Cuenta

### ¿Por qué múltiples cuentas?

Como el cooldown es **por cuenta**, añadir varias cuentas de Google permite generar imágenes en paralelo. El sistema rotará automáticamente entre todas las cuentas configuradas hasta encontrar una disponible.

### Configuración

```bash
# Añadir slot de cuenta
python3 antigravity_cli.py accounts add trabajo --label "Cuenta de Trabajo"

# Login con una cuenta de Google diferente
python3 antigravity_cli.py login --account trabajo

# Listar todas las cuentas
python3 antigravity_cli.py accounts

# Generar — failover automático a cuenta B si cuenta A está en cooldown
python3 antigravity_cli.py img "Un atardecer" -o atardecer.png
```

### Flujo de Auto-Failover

```
Cuenta A (activa) → is_on_cooldown? Sí (20 min rest.) → Saltando...
Cuenta B          → intenta generar → Error 429 → Cooldown 1h → Siguiente...
Cuenta C          → ✅ genera imagen → Cooldown 5 min
```

---

## Estructura de la Petición API

### Petición de Generación de Imagen

```json
{
    "project": "instant-anthem-5bxbf",
    "model": "gemini-3.1-flash-image",
    "request": {
        "contents": [
            {"role": "user", "parts": [{"text": "Un gato lindo con gafas de sol"}]}
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

La **configuración de seguridad** se pone en `"OFF"` para evitar bloqueos por filtrado de contenido del servidor.

---

## Estructura de Archivos

```
antigravity-studio/
├── antigravity_auth.py       # OAuth2 PKCE, código dispositivo, refresco token, extracción email
├── antigravity_client.py     # Cliente API: chat, imagen, modelos, resolución de proyecto
├── antigravity_cli.py        # Comandos CLI: login, chat, img, cuentas
├── auth_cooldown.py          # Gestión de cooldown persistente por cuenta (SQLite)
├── auth.json                 # Credenciales (seguro para commit, tokens expiran en 1 hora)
├── requirements.txt          # Solo: requests>=2.31.0
├── test_auth.py              # 27 pruebas de auth
├── test_client.py            # 10 pruebas de cliente
└── docs/                     # Documentación técnica extendida
```

### Constantes Clave

| Constante | Valor | Propósito |
|-----------|-------|-----------|
| `AUTH_COOLDOWN_SECONDS` | 300s | Cooldown estándar tras éxito |
| `AUTH_429_COOLDOWN_SECONDS` | 3600s | Penalización tras error 429 |
| `BASE_URL_FALLBACKS` | 3 URLs | Cadena de endpoints: Sandbox → Daily → Prod |
| `FALLBACK_PROJECT_ID` | `bamboo-precept-lgxtn` | Proyecto compartido nivel gratuito |

---

## Registro de Cambios (Changelog)

### v2.1 — Cooldown por Cuenta

**Refactorización de Cooldown**
- Cambiado sistema de cooldown global por uno **específico por cuenta**.
- Nuevo esquema SQLite en `auth_cooldown.py` con `account` como clave primaria.
- Implementada penalización de 1 hora para cuentas que reciben error 429.
- Implementado auto-failover inteligente: el CLI salta cuentas bloqueadas sin esperas.

**Mejoras en CLI**
- Nueva tabla resumen detallando el estado de cada cuenta intentada.
- Fallback automático: si todas están bloqueadas, espera por la que se libera primero (si es < 5 min).

### v2.0 — Mejoras de Antigravity-Manager

**Cadena de Fallback de Endpoints**
- Añadido fallback de endpoints en 3 niveles: Sandbox → Daily → Prod.
- Fuente: Antigravity-Manager `src-tauri/src/proxy/upstream/client.rs`.

**Resolución de ID de Proyecto**
- Añadido `FALLBACK_PROJECT_ID = "bamboo-precept-lgxtn"` para cuentas gratuitas.
- Fuente: Antigravity-Manager `src-tauri/src/proxy/project_resolver.rs`.

### v1.0 — Port Inicial

- Login OAuth2 PKCE.
- Consultas de chat y generación de imágenes.
- Soporte multi-cuenta.

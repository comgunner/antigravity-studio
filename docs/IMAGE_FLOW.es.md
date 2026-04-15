# Flujo de Generación de Imágenes

Recorrido paso a paso de cómo `antigravity_cli.py img` genera una imagen.

---

## Ejemplo de Salida

```
$ python3 antigravity_cli.py img "Un perro lindo con gafas de sol" -o gato.png
Modelo: gemini-3.1-flash-image
Prompt: Un perro lindo con gafas de sol
Generando imagen...
⚠ La cuenta 'Default' está en cooldown, intentando con la siguiente...
✓ Generada usando la cuenta: trabajo
✓ Imagen guardada: gato.png (887,449 bytes)
⏱ Tiempo de generación: 39s

⏳ Cooldown: esperando 300s antes de la siguiente generación (protección anti-ban)...
✓ Cooldown completado.

============================================================
📊 RESUMEN DE INTENTOS
============================================================
Cuenta               Estado             Tiempo   Detalles
────────────────────────────────────────────────────────────
  Default            429 COOLDOWN       0s
  trabajo            SUCCESS           39s (887,449 bytes)
────────────────────────────────────────────────────────────
  ✅ ÉXITO | Tiempo total: 342s | Intentos: 2
============================================================
```

---

## Diagrama de Flujo

```
Usuario ejecuta: python3 antigravity_cli.py img "prompt" -o salida.png
│
├─► 1. PROCESAR ARGUMENTOS
│    ├── prompt:     "Un perro lindo con gafas de sol"
│    ├── modelo:      gemini-3.1-flash-image (por defecto)
│    ├── salida:      gato.png
│    ├── cooldown:   300s (por defecto, configurable con --cooldown)
│    └── aspecto:     1:1 (por defecto)
│
├─► 2. CARGAR CUENTAS
│    ├── Leer auth.json → descubrir todas las credenciales
│    ├── Leer antigravity_config.json → obtener nombres de cuentas
│    ├── Orden: cuenta activa primero, luego las demás
│    └── Ejemplo: [Default(activa), trabajo, trabajo2]
│
├─► 3. INTENTAR CUENTAS (bucle fail-fast)
│    │
│    ├─► Cuenta: Default (activa)
│    │   ├── Obtener token válido → refrescar si ha expirado
│    │   ├── Crear AntigravityClient(token, project_id)
│    │   │
│    │   ├──► generate_image()
│    │   │   ├── Procesar prompt (soporta JSON con campo "prompt")
│    │   │   ├── Limpiar prefijos de modelo
│    │   │   ├── Construir partes: [{"text": "Un perro lindo..."}]
│    │   │   ├── Construir sobre (envelope):
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
│    │   │   ├──► CADENA DE FALLBACK DE ENDPOINTS
│    │   │   │   ├── Intentar: daily-cloudcode-pa.sandbox.googleapis.com
│    │   │   │   │   └── Estado: 429 → intentar siguiente
│    │   │   │   ├── Intentar: daily-cloudcode-pa.googleapis.com
│    │   │   │   │   └── Estado: 429 → intentar siguiente
│    │   │   │   └── Intentar: cloudcode-pa.googleapis.com
│    │   │   │       └── Estado: 429 → todos los endpoints agotados
│    │   │   │
│    │   │   └── Resultado: HTTPError 429 → FAIL FAST (espera 0s)
│    │   │
│    │   └── CLI captura 429 → "⚠ La cuenta 'Default' está en cooldown, intentando..."
│    │
│    ├─► Cuenta: trabajo
│    │   ├── Obtener token válido
│    │   ├── Crear AntigravityClient(token, project_id)
│    │   │
│    │   ├──► generate_image()
│    │   │   ├── Mismo sobre que el anterior
│    │   │   │
│    │   │   ├──► CADENA DE FALLBACK DE ENDPOINTS
│    │   │   │   ├── Intentar: daily-cloudcode-pa.sandbox.googleapis.com
│    │   │   │   │   └── Estado: 200 ✅ ÉXITO
│    │   │   │   └── (no es necesario intentar Daily/Prod)
│    │   │   │
│    │   │   ├── Extraer imagen base64 de la respuesta
│    │   │   │   └── candidates[0].content.parts[0].inlineData.data
│    │   │   └── Decodificar base64 → devolver bytes (887,449 bytes)
│    │   │
│    │   └── ¡ÉXITO!
│    │
│    └─► (Se omiten las cuentas restantes — ya obtuvimos la imagen)
│
├─► 4. GUARDAR IMAGEN
│    ├── Escribir bytes en: gato.png
│    ├── Imprimir: "✓ Imagen guardada: gato.png (887,449 bytes)"
│    └── Imprimir: "⏱ Tiempo de generación: 39s"
│
├─► 5. COOLDOWN OBLIGATORIO
│    ├── Esperar 300s (5 min) — protección anti-ban
│    ├── Configurable: --cooldown 600 (10 min), --cooldown 0 (ninguno)
│    └── Imprimir: "⏳ Cooldown: esperando 300s... ✓ Cooldown completado."
│
├─► 6. RESUMEN DE INTENTOS
│    ├── Imprimir tabla con todos los intentos:
│    │   - Nombre de la cuenta
│    │   - Estado (429 COOLDOWN / SUCCESS / 500 ERROR / ERROR)
│    │   - Tiempo transcurrido
│    │   - Detalles (tamaño del archivo o mensaje de error)
│    └── Imprimir: "✅ ÉXITO | Tiempo total: 342s | Intentos: 2"
│
└─► 7. SALIDA
     └── El proceso termina correctamente (exit 0)
```

---

## Cadena de Fallback de Endpoints (Detalle)

Cada llamada a la API (chat o imagen) intenta 3 endpoints **en orden**:

```
Prioridad 1: https://daily-cloudcode-pa.sandbox.googleapis.com/v1internal
Prioridad 2: https://daily-cloudcode-pa.googleapis.com/v1internal
Prioridad 3: https://cloudcode-pa.googleapis.com/v1internal
```

**Comportamiento:**
- Si el endpoint devuelve **200** → se usa, deja de intentar los demás
- Si el endpoint devuelve **429/500/503** → intenta con el siguiente endpoint
- Si el endpoint devuelve **otro error** (400, 401, 403, etc.) → se detiene y lanza el error

**Por qué es importante:**
- El **Sandbox** tiene menos tráfico y menos restricciones de rate limit
- Si los 3 endpoints devuelven 429 → la cuenta está totalmente en cooldown
- El fallback da **3 veces más oportunidades** de conectar por cuenta

---

## Failover de Cuenta (Detalle)

```
Para cada cuenta (la activa primero):
    │
    ├── Obtener token válido
    │   └── Si ha expirado → auto-refresco
    │   └── Si no hay token de refresco → solicitar login
    │
    ├── Crear cliente
    │
    ├── Intentar generate_image()
    │   │
    │   ├── Intentar endpoint 1 (Sandbox)
    │   │   └── 429 → intentar endpoint 2
    │   ├── Intentar endpoint 2 (Daily)
    │   │   └── 429 → intentar endpoint 3
    │   ├── Intentar endpoint 3 (Prod)
    │   │   └── 429 → lanzar HTTPError 429
    │   │
    │   └── Resultado: error 429
    │
    ├── CLI captura 429 → "intentando con la siguiente cuenta"
    │   └── SIN ESPERA — failover instantáneo
    │
    └── Siguiente cuenta → repetir...
```

**Diferencia clave con el comportamiento anterior:**

| Anterior | Nuevo |
|----------|-------|
| 30s de espera al primer 429 | **0s de espera** — siguiente cuenta al instante |
| Solo endpoint de Prod | **3 endpoints** por cuenta |
| Una sola cuenta | **Auto-intento de todas las cuentas** |
| Sin info de tiempos | **Tabla resumen** con tiempos |

---

## Lógica de Cooldown

### Tras generación EXITOSA

```
Imagen generada → Guardar archivo → Iniciar temporizador de cooldown → Esperar → Imprimir resumen → Salir
```

**Propósito:** Prevenir baneos por peticiones sucesivas rápidas de imágenes.

**Por defecto:** 300 segundos (5 minutos) — basado en pruebas reales que muestran un cooldown real de la API de 5-10 min.

**Personalizar:**
```bash
--cooldown 600   # 10 minutos (más seguro)
--cooldown 120   # 2 minutos (más rápido, más riesgoso)
--cooldown 0     # Sin cooldown (alto riesgo de baneo)
```

### En caso de 429 (límite excedido)

```
429 recibido → Registrar "429 COOLDOWN" → Siguiente cuenta → SIN ESPERA
```

**Sin esperas** entre intentos de cuenta. El CLI pasa a la siguiente cuenta instantáneamente.

### Todas las cuentas en cooldown

```
Todas las cuentas intentadas → Todas devolvieron 429 → Imprimir resumen → Salir con error
```

```
❌ Todas las cuentas están con rate limit. Por favor, espera 5-10 minutos e intenta de nuevo.
```

---

## Escenarios de Error

### Escenario 1: Cuenta A en cooldown, B tiene éxito

```
Cuenta A → 429 → ⚠ cooldown
Cuenta B → 200 → ✅ imagen guardada → 5 min cooldown → resumen → salir
```

### Escenario 2: Todas las cuentas en cooldown

```
Cuenta A → 429 → ⚠ cooldown
Cuenta B → 429 → ⚠ cooldown
Cuenta C → 429 → ⚠ cooldown
Todas agotadas → ❌ esperar 5-10 min
```

### Escenario 3: Error 500 (ID de proyecto inválido)

```
Cuenta A → 500 → ⚠ error de servidor, intentar siguiente
Cuenta B → 200 → ✅ imagen guardada
```

### Escenario 4: Cuenta única, en cooldown

```
Cuenta A → 429 → todos los endpoints intentados → ❌ esperar 5-10 min
```

---

## Desglose de Tiempos (del ejemplo)

```
Tiempo total: 342s
├── Cuenta 'Default': 0s (429 — falla rápido, ningún endpoint respondió con 200)
├── Cuenta 'trabajo':   39s (200 — generación completa vía endpoint Sandbox)
└── Cooldown:         300s (5 min de espera obligatoria)
                      ─────
                      339s (+ 3s de overhead = 342s total)
```

---

## Payload de la Petición (Lo que se envía)

```json
{
    "project": "instant-anthem-5bxbf",
    "model": "gemini-3.1-flash-image",
    "request": {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Un perro lindo con gafas de sol"}
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

## Estructura de la Respuesta (Lo que vuelve)

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

El `inlineData.data` son los bytes de la imagen en **base64**. El cliente los decodifica y guarda en el disco.

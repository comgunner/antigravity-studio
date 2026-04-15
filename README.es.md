# antigravity-studio

Cliente de Google Antigravity (Cloud Code Assist) en Python puro — chat de texto + generación de imágenes + tareas agénticas.

Mejorado con estrategias del proyecto en Rust [Antigravity-Manager](https://github.com/lbjlaq/Antigravity-Manager).

**Características clave:** Fallback de endpoints en 3 niveles (Sandbox → Daily → Prod), fallback de ID de proyecto para nivel gratuito,
configuración de seguridad desactivada (OFF), auto-failover entre cuentas, cooldown obligatorio después de la generación de imágenes.

## Instalar

### 1. Acceso CLI Global (NPM)
Instala el estudio globalmente para acceder al comando desde cualquier lugar:

```bash
npm install -g @comgunner/antigravity-studio
```

### 2. Configuración del Entorno Python
Dado que la lógica central se basa en Python, necesitas configurar el entorno en la ubicación del paquete:

```bash
# Navega al paquete instalado (o a tu repo clonado)
cd $(antigravity-studio path | xargs dirname)

# Crear y activar entorno virtual
python3.12 -m venv .venv
source .venv/bin/activate

# Actualizar herramientas base e instalar dependencias
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

## Integración con Picoclaw-Agents (Como Skill)

Si usas `picoclaw-agents`, puedes instalar este estudio como una Skill automáticamente:

```bash
# Instalar como Skill para Picoclaw
antigravity-studio install --target picoclaw

# Otros destinos: --target claude, --target agents
```

## Inicio Rápido

### 1. Login

```bash
# OAuth por Navegador (recomendado)
python3 antigravity_cli.py login

# Login en una cuenta específica
python3 antigravity_cli.py login --account trabajo

# Headless / SSH / Termux
python3 antigravity_cli.py login --device
```

### 1b. Configuración Multi-Cuenta

```bash
# Agregar una segunda cuenta
python3 antigravity_cli.py accounts add trabajo

# Iniciar sesión en ella (abre el navegador)
python3 antigravity_cli.py login --account trabajo

# Listar todas las cuentas (muestra estado, emails, IDs de proyecto)
python3 antigravity_cli.py accounts

# Cambiar de cuenta activa
python3 antigravity_cli.py accounts switch trabajo
```

### 2. Listar Modelos

```bash
python3 antigravity_cli.py models
```

**Ejemplo de Salida:**
```text
Available Antigravity Models:
────────────────────────────────────────────────────────────
  ✓ claude-opus-4-6-thinking (Claude Opus 4.6 (Thinking))
  ✓ claude-sonnet-4-6 (Claude Sonnet 4.6 (Thinking))
  ✓ gemini-2.5-flash (Gemini 3.1 Flash Lite)
  ✓ gemini-2.5-flash-lite (Gemini 3.1 Flash Lite)
  ✓ gemini-2.5-flash-thinking (Gemini 3.1 Flash Lite)
  ✓ gemini-2.5-pro (Gemini 2.5 Pro)
  ✓ gemini-3-flash (Gemini 3 Flash)
  ✓ gemini-3-flash-agent (Gemini 3 Flash)
  ✓ gemini-3-pro-high (Gemini 3 Pro (High))
  ✓ gemini-3-pro-low (Gemini 3 Pro (Low))
  ✓ gemini-3.1-flash-image (Gemini 3.1 Flash Image)
  ✓ gemini-3.1-flash-lite (Gemini 3.1 Flash Lite)
  ✓ gemini-3.1-pro-high (Gemini 3.1 Pro (High))
  ✓ gemini-3.1-pro-low (Gemini 3.1 Pro (Low))
  ✓ gpt-oss-120b-medium (GPT-OSS 120B (Medium))
```

### 3. Chat

```bash
python3 antigravity_cli.py chat "¿Cuál es la capital de Francia?"
python3 antigravity_cli.py chat "Escribe un poema" --model gemini-3-flash
```

#### Usando `gemini-3-flash-agent`

El modelo `gemini-3-flash-agent` soporta **capacidades agénticas** — puede usar herramientas, ejecutar código y realizar razonamientos en múltiples pasos:

```bash
# Chat básico con agente
python3 antigravity_cli.py chat "Analiza este código Python y sugiere mejoras" --model gemini-3-flash-agent

# Agente con una tarea compleja
python3 antigravity_cli.py chat "Escribe una función para ordenar una lista, luego pruébala con 5 casos borde" --model gemini-3-flash-agent

# Agente con contexto extendido
python3 antigravity_cli.py chat "Depura este error: IndexError: list index out of range" \
  --model gemini-3-flash-agent --max-tokens 8192
```

### 4. Resumen Técnico (Análisis Multi-Activo)

Genera resúmenes técnicos para Cripto (Binance), Metales, Forex e Índices (Yahoo Finance). Esta función calcula EMAs (3, 9, 21, 50, 200) y utiliza Gemini para proporcionar un análisis narrativo.

**Activos Soportados (Yahoo Finance):**
- **Metales:** `xau` (Oro), `xag` (Plata)
- **Forex:** `eurusd`, `gbpusd`, `jpymxn`, `mxn`
- **Índices:** `gspc` (S&P 500), `ixic` (Nasdaq), `dxy` (Dólar Index)
- **Commodities:** `cl` (Petróleo WTI)
- **Cripto (Binance):** `btc`, `eth`, `sol`, `ada`, etc.

```bash
# 1. Cripto Estándar (Binance)
python3 antigravity_cli.py --resume btc

# 2. Oro (Yahoo: Futuros de Oro GC=F)
python3 antigravity_cli.py --resume xau

# 3. Nasdaq (^IXIC)
python3 antigravity_cli.py --resume ixic --tf 1h
```

**Ejemplo de Salida (BTC):**

![Resumen BTC](assets/result_resume_btc.png)

```text
--- Generating BTC 4h Summary with Gemini ---
CURRENT STATUS: BTC (4h)
Price: $74,520.3 (0.56%)
EMA 3:   74210.15 | EMA 9:   73990.86
EMA 21:  73158.25 | EMA 50:  71894.85 | EMA 200: 69932.71

--- AI TECHNICAL VIEW (GEMINI) ---
**Sentiment: Strongly Bullish**, as price holds above all major EMAs (3, 9, 21, 50, 200) in a clear technical uptrend.
```

**Ejemplo de Salida (Oro):**

![Resumen XAU](assets/result_resume_xau.png)

```text
--- Generating XAU 1h Summary with Gemini ---
CURRENT STATUS: XAU (1h) | SOURCE: Yahoo Finance
Price: $4,872.8 (0.27%)
EMA 3:   4866.66 | EMA 9:   4856.08
EMA 21:  4833.55 | EMA 50:  4804.68 | EMA 200: 4748.71
```

**Ejemplo de Salida (Petróleo Crudo):**

![Resumen CL](assets/result_resume_cl.png)

```text
--- Generating CL 1h Summary with Gemini ---
CURRENT STATUS: CL (1h) | SOURCE: Yahoo Finance
Price: $90.15 (-0.23%)
EMA 3:   90.44 | EMA 9:   91.57
EMA 21:  93.59 | EMA 50:  96.28 | EMA 200: 99.74
```

### 5. Generar Imágenes

#### Prompt Simple
```bash
python3 antigravity_cli.py img "Un gato lindo con gafas de sol" -o gato.png
```
![Resultado Gato](assets/result_cat.png)

#### Relación de Aspecto y Alto Detalle
```bash
python3 antigravity_cli.py img "Neo de Matrix... código cayendo" --aspect-ratio 4:5 -o neo.png
```
![Resultado Neo](assets/result_neo.png)

#### Retrato Cinemático
```bash
python3 antigravity_cli.py img "Retrato de un guerrero" --aspect-ratio 9:16 -o guerrero.png
```
![Resultado Guerrero](assets/result_warrior.png)

#### Avanzado: Prompt JSON con Imagen de Referencia
```bash
python3 antigravity_cli.py img '{                                                         
    "id": 1,
    "theme": "Python Coding",
    "prompt": "A promotional graphic with a dark high-tech background. In the center, a 3D stylized Python logo with a glowing blue and yellow circuit board pattern, digital steam rising. Top center: include the logo from the reference image. Bottom text in bold white sans-serif: Python without Errors. Minimalist, clean, high quality 3D render."
}' -r ./logo/logo_python.png -o python_no_errors.png
```
![Resultado Python No Errors](assets/result_python_no_errors.png)

## Estructura del Proyecto

| Archivo | Propósito |
|---------|-----------|
| `antigravity_cli.py` | Punto de entrada principal para todos los comandos |
| `coin_summary.py` | Lógica de análisis técnico multi-activo |
| `bin/cli.js` | Lógica del instalador global de NPM |
| `SKILL.md` | Manifiesto de capacidades para agentes IA |

## Licencia

Este proyecto está bajo la licencia **GNU General Public License v3.0**. Consulta el archivo [LICENSE.md](LICENSE.md) file for details.

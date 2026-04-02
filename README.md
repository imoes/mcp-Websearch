# llama.cpp + DuckDuckGo Websuche

Dieses Projekt ermöglicht eine DuckDuckGo-Websuche aus dem llama.cpp Chat heraus — automatisch ausgelöst durch Begriffe wie **"recherchiere"** oder **"mache eine Websuche"**. Die ersten 25 Suchergebnisse werden berücksichtigt.

Es gibt zwei Wege:

| | Weg A: MCP-Server (WebUI) | Weg B: Python-Client (Terminal) |
|---|---|---|
| Interface | Browser (`http://127.0.0.1:8080`) | Terminal |
| Technologie | MCP via SSE + `--webui-mcp-proxy` | OpenAI-API + Function Calling |
| Stabilität | Experimentell (llama.cpp v.b3495+) | Stabil |
| Einrichtung | Etwas mehr Schritte | Einfacher |

---

## Voraussetzungen

- Windows 10/11, Linux oder macOS
- Python 3.10 oder neuer
- Git
- ca. 8 GB RAM (für ein 7B-Modell, quantisiert)
- GPU optional (CUDA, Metal oder Vulkan)

---

## Schritt 1: llama.cpp installieren

### Option A: Vorkompilierte Binaries (empfohlen für Windows)

1. Gehe zu den [llama.cpp Releases](https://github.com/ggml-org/llama.cpp/releases)
2. Lade das passende Archiv herunter:
   - **Windows CPU:** `llama-...-bin-win-cpu-x64.zip`
   - **Windows CUDA (NVIDIA):** `llama-...-bin-win-cuda-cu12.x-x64.zip`
   - **Windows Vulkan:** `llama-...-bin-win-vulkan-x64.zip`
3. Entpacke nach z.B. `C:\llama.cpp\`

### Option B: Selbst kompilieren (Linux/macOS)

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_CUDA=ON    # ohne CUDA: cmake -B build
cmake --build build --config Release -j$(nproc)
```

---

## Schritt 2: Modell herunterladen

Du benötigst ein Modell mit **Function-Calling-Support**:

| Modell | Größe | Empfehlung |
|--------|-------|------------|
| Qwen2.5-7B-Instruct-Q4_K_M | ~4.5 GB | Beste Tool-Unterstützung |
| Llama-3.1-8B-Instruct-Q4_K_M | ~4.9 GB | Sehr gut |
| Mistral-7B-Instruct-v0.3-Q4_K_M | ~4.1 GB | Gut |

```bash
pip install huggingface-hub

huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
  qwen2.5-7b-instruct-q4_k_m.gguf \
  --local-dir ./models/
```

---

## Schritt 3: Python-Umgebung einrichten

```bash
cd mcp-Websearch

python -m venv .venv

# Aktivieren:
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Weg A: MCP-Server + llama.cpp WebUI (Browser-Chat)

### Wie es funktioniert

```
Browser (http://127.0.0.1:8080)
  │
  ▼
llama-server (--webui-mcp-proxy, Port 8080)
  │  leitet MCP-Anfragen weiter
  ▼
mcp_server.py (SSE, Port 3001)
  │  führt Suche aus
  ▼
DuckDuckGo (25 Ergebnisse)
```

### A.1 — llama-server mit MCP-Proxy starten

**Windows:**
```cmd
llama-server.exe ^
  --model models\qwen2.5-7b-instruct-q4_k_m.gguf ^
  --ctx-size 8192 ^
  --n-predict 2048 ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --jinja ^
  --webui-mcp-proxy
```

**Linux/macOS:**
```bash
./build/bin/llama-server \
  --model models/qwen2.5-7b-instruct-q4_k_m.gguf \
  --ctx-size 8192 \
  --n-predict 2048 \
  --host 127.0.0.1 \
  --port 8080 \
  --jinja \
  --webui-mcp-proxy
```

> `--jinja` ist für korrekte Tool-Call-Templates nötig.
> `--webui-mcp-proxy` aktiviert den MCP-CORS-Proxy (experimentell seit b3495).

### A.2 — MCP-Server starten

In einem **zweiten Terminal** (venv aktiviert):

#### DuckDuckGo (Standard, kein API-Key nötig)
```bash
python mcp_server.py
```

#### Google Custom Search
Benötigt einen [Google API-Key](https://developers.google.com/custom-search/v1/introduction) und eine [Custom Search Engine ID (CX)](https://programmablesearchengine.google.com/):
```bash
python mcp_server.py --provider google --api-key AIzaSy... --cx 123456789:abc
```
> Kostenloses Kontingent: 100 Suchanfragen/Tag. Pro Suche werden bis zu 3 API-Aufrufe gemacht (à 10 Ergebnisse = 25 Treffer).

#### Brave Search
Benötigt einen [Brave Search API-Key](https://brave.com/search/api/):
```bash
python mcp_server.py --provider brave --api-key BSAx...
```
> Free-Tier: 2.000 Suchanfragen/Monat.

#### Allgemeine Optionen
```
python mcp_server.py --help

  --provider  {duckduckgo,google,brave}   Suchanbieter (default: duckduckgo)
  --api-key   API_KEY                     API-Key für Google oder Brave
  --cx        CX                          Google Custom Search Engine ID
  --host      HOST                        Host (default: 0.0.0.0)
  --port      PORT                        Port (default: 3001)
```

### A.3 — MCP-Server in der WebUI verbinden

1. Öffne `http://127.0.0.1:8080` im Browser
2. Klicke oben rechts auf das **Einstellungen-Icon** (Zahnrad)
3. Navigiere zu **MCP Servers** oder **Tools**
4. Klicke auf **"+ Add MCP Server"** oder das **Stift-Icon**
5. Trage ein:
   - **URL:** `http://127.0.0.1:3001/sse`
   - **Name:** `DuckDuckGo` (beliebig)
6. Aktiviere den Toggle **"Use llama-server proxy"**
7. Speichern / Verbinden

Das Tool `web_search` sollte jetzt in der WebUI als verfügbar angezeigt werden.

### A.4 — Benutzen

Im Browser-Chat einfach eingeben:
```
recherchiere aktuelle Python 3.13 Features
mache eine Websuche zu llama.cpp Benchmark 2025
was kostet eine RTX 5090?
```

> **Hinweis:** Der `--webui-mcp-proxy` ist seit llama.cpp b3495 verfügbar und noch
> als experimentell markiert. Falls die Verbindung nicht klappt, nutze Weg B.

---

## Weg B: Python Chat-Client (Terminal)

Stabiler Fallback ohne experimentelle Features.

### Wie es funktioniert

```
Terminal (chat.py)
  │  sendet Nachricht + Tool-Definition
  ▼
llama-server (Port 8080, ohne --webui-mcp-proxy)
  │  gibt Tool-Call zurück
  ▼
chat.py führt DuckDuckGo-Suche aus (25 Ergebnisse)
  │  sendet Ergebnis zurück
  ▼
llama-server formuliert finale Antwort
```

### B.1 — llama-server starten (ohne `--webui-mcp-proxy`)

**Windows:**
```cmd
llama-server.exe ^
  --model models\qwen2.5-7b-instruct-q4_k_m.gguf ^
  --ctx-size 8192 ^
  --n-predict 2048 ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --jinja
```

### B.2 — Chat starten

```bash
python chat.py
```

```
============================================================
  llama.cpp Chat mit DuckDuckGo Websuche
============================================================
Befehle: 'exit' oder 'quit' zum Beenden
Tipp: Sage 'recherchiere [Thema]' für eine Websuche
============================================================

Du: recherchiere llama.cpp aktuelle Version
[Websuche] Suche nach: "llama.cpp aktuelle Version" ...
[Websuche] 25 Ergebnisse gefunden.

Assistent: ...
```

---

## Projektstruktur

```
mcp-Websearch/
├── README.md
├── requirements.txt
├── chat.py          ← Weg B: Terminal-Chat-Client
├── mcp_server.py    ← Weg A: MCP-Server für llama.cpp WebUI
└── models/          ← GGUF-Modelldateien (manuell anlegen)
```

---

## GPU-Beschleunigung

Füge beim Server-Start `--n-gpu-layers N` hinzu:

| VRAM | Empfohlener Wert |
|------|-----------------|
| 4 GB | `--n-gpu-layers 15` |
| 6 GB | `--n-gpu-layers 25` |
| 8 GB | `--n-gpu-layers 35` |
| 12 GB+ | `--n-gpu-layers 99` (alle Layer) |

---

## Fehlerbehebung

### MCP-Server verbindet sich nicht in der WebUI
- Stelle sicher, dass `--webui-mcp-proxy` beim llama-server aktiv ist
- Prüfe, ob `mcp_server.py` läuft: `http://127.0.0.1:3001/sse` im Browser aufrufen (muss eine SSE-Verbindung öffnen)
- Versuche den Toggle "Use llama-server proxy" aus- und wieder einzuschalten
- Fallback: Nutze Weg B

### `Connection refused` bei chat.py
Der llama-server läuft nicht. Starte ihn zuerst.

### Modell ignoriert Tool-Calls
- `--jinja` Flag beim Server vergessen?
- Qwen2.5 und Llama 3.1 haben die beste Tool-Unterstützung
- Kleinere Modelle (< 3B) oft unzuverlässig

### DuckDuckGo liefert keine Ergebnisse
DuckDuckGo begrenzt manchmal Anfragen. Kurz warten und erneut versuchen.

### `ImportError: cannot import name 'DDGS'`
```bash
pip install --upgrade duckduckgo-search
```

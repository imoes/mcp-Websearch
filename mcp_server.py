"""
Websuche MCP-Server für llama.cpp WebUI
Verbinde ihn in der llama.cpp WebUI über:
  http://<server-ip>:3001/mcp

Unterstützte Suchanbieter:
  --provider duckduckgo          (Standard, kein API-Key nötig)
  --provider google              (benötigt --api-key und --cx)
  --provider brave               (benötigt --api-key)

Beispiele:
  python mcp_server.py
  python mcp_server.py --provider google --api-key AIza... --cx 123:abc
  python mcp_server.py --provider brave  --api-key BSA...
  python mcp_server.py --proxy http://user:pass@proxy.example.com:8080

Proxy-Konfiguration (Priorität: --proxy > Umgebungsvariable SEARCH_PROXY):
  Umgebungsvariable: SEARCH_PROXY=http://proxy.example.com:8080
"""

import argparse
import os
import socket
import math
import urllib.parse
import urllib.request
import json
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware

# ── Konfiguration ────────────────────────────────────────────────────────────
DEFAULT_HOST       = "0.0.0.0"
DEFAULT_PORT       = 3001
MAX_SEARCH_RESULTS = 25
# ─────────────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Websuche MCP-Server für llama.cpp",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=__doc__
)
parser.add_argument("--host",     default=DEFAULT_HOST,    help=f"Host (default: {DEFAULT_HOST})")
parser.add_argument("--port",     type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
parser.add_argument("--provider", default="duckduckgo",
                    choices=["duckduckgo", "google", "brave"],
                    help="Suchanbieter (default: duckduckgo)")
parser.add_argument("--api-key",  default="",
                    help="API-Key für Google oder Brave (nicht nötig für DuckDuckGo)")
parser.add_argument("--cx",       default="",
                    help="Google Custom Search Engine ID (nur für --provider google)")
parser.add_argument("--proxy",    default="",
                    help="Proxy-URL (überschreibt Umgebungsvariable SEARCH_PROXY), "
                         "z.B. http://user:pass@proxy.example.com:8080")
args = parser.parse_args()

# ── Proxy auflösen (Priorität: --proxy > SEARCH_PROXY > http_proxy/https_proxy) ──
# Stufe 1: expliziter Parameter
# Stufe 2: eigene Umgebungsvariable SEARCH_PROXY
# Stufe 3: Systemvariablen http_proxy / https_proxy (werden von urllib und
#           httpx/ddgs automatisch gelesen, wenn PROXY_URL leer bleibt)
PROXY_URL: str = args.proxy or os.environ.get("SEARCH_PROXY", "")

_SYS_HTTP_PROXY  = os.environ.get("http_proxy")  or os.environ.get("HTTP_PROXY",  "")
_SYS_HTTPS_PROXY = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY", "")
_SYS_NO_PROXY    = os.environ.get("no_proxy")    or os.environ.get("NO_PROXY",    "")

# ── Validierung ───────────────────────────────────────────────────────────────
if args.provider == "google" and (not args.api_key or not args.cx):
    parser.error("--provider google benötigt --api-key UND --cx")
if args.provider == "brave" and not args.api_key:
    parser.error("--provider brave benötigt --api-key")

PROVIDER_LABELS = {
    "duckduckgo": "DuckDuckGo",
    "google":     "Google",
    "brave":      "Brave Search",
}

INSTRUCTIONS = f"""
Du hast Zugriff auf das Tool `web_search` ({PROVIDER_LABELS[args.provider]}), \
mit dem du aktuelle Informationen aus dem Internet abrufen kannst.

Nutze `web_search` IMMER in folgenden Situationen:
- Der Nutzer fragt nach aktuellen Ereignissen, Nachrichten oder Entwicklungen
- Der Nutzer fragt nach Preisen, Kursen, Wetterdaten oder anderen sich ändernden Informationen
- Dein Trainingswissen könnte veraltet sein (älter als 1-2 Jahre)
- Du bist dir nicht sicher, ob deine gespeicherten Informationen noch korrekt sind
- Der Nutzer sagt etwas wie: "suche", "such", "google", "recherchiere", "finde heraus", \
"was ist aktuell", "neueste", "aktuelle", "heutige"
- Der Nutzer stellt eine Frage, auf die du keine zuverlässige Antwort aus deinem Training geben kannst

Nutze `web_search` NICHT bei:
- Allgemeinen Wissensfragen zu stabilen Fakten (Mathematik, Grammatik, Programmierkonzepte)
- Aufgaben wie Texte schreiben, Code erklären oder umformulieren

Führe die Suche immer zuerst durch, bevor du antwortest, wenn einer der obigen Punkte zutrifft.

Nach einer Websuche MUSST du folgendes Format einhalten:
- Setze im Fließtext Fußnoten in eckigen Klammern [1], [2], ... direkt nach der jeweiligen Information
- Jede Fußnotennummer entspricht der "Quelle [N]"-Nummer aus den Suchergebnissen
- Verwende nur Quellen, die du tatsächlich zitierst — nicht alle 25 auflisten
- Schreibe am Ende deiner Antwort einen Abschnitt "**Quellen:**" mit den zitierten Quellen als Markdown-Links:

  **Quellen:**
  [1] [Titel der Seite](https://url.example.com)
  [2] [Titel der Seite](https://url.example.com)
"""

mcp = FastMCP(
    f"{PROVIDER_LABELS[args.provider]} Websuche",
    instructions=INSTRUCTIONS,
    host=args.host,
    port=args.port,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


# ── Suchanbieter-Implementierungen ────────────────────────────────────────────

def _make_opener() -> urllib.request.OpenerDirector:
    """Erstellt einen urllib-Opener mit optionalem Proxy."""
    if PROXY_URL:
        proxy_handler = urllib.request.ProxyHandler({
            "http":  PROXY_URL,
            "https": PROXY_URL,
        })
        return urllib.request.build_opener(proxy_handler)
    return urllib.request.build_opener()


def _search_duckduckgo(query: str, region: str) -> list[dict]:
    """DuckDuckGo-Suche via ddgs (kein API-Key nötig)."""
    from ddgs import DDGS
    with DDGS(proxy=PROXY_URL or None) as ddgs:
        return list(ddgs.text(
            query,
            region=region,
            safesearch="moderate",
            max_results=MAX_SEARCH_RESULTS
        ))


def _search_google(query: str, region: str) -> list[dict]:
    """Google Custom Search API (benötigt API-Key + CX).
    Gibt bis zu 25 Ergebnisse zurück (3 API-Aufrufe à max. 10 Treffer).
    """
    results = []
    per_page = 10
    pages_needed = math.ceil(MAX_SEARCH_RESULTS / per_page)
    lang = region.split("-")[0] if "-" in region else region

    for page in range(pages_needed):
        start = page * per_page + 1
        num   = min(per_page, MAX_SEARCH_RESULTS - len(results))
        params = urllib.parse.urlencode({
            "key": args.api_key,
            "cx":  args.cx,
            "q":   query,
            "num": num,
            "start": start,
            "lr":  f"lang_{lang}",
        })
        url = f"https://www.googleapis.com/customsearch/v1?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "mcp-websearch/1.0"})
        with _make_opener().open(req, timeout=10) as resp:
            data = json.loads(resp.read())

        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "href":  item.get("link", ""),
                "body":  item.get("snippet", ""),
            })

        if len(data.get("items", [])) < per_page:
            break   # keine weiteren Seiten verfügbar

    return results


def _search_brave(query: str, region: str) -> list[dict]:
    """Brave Search API (benötigt API-Key).
    Gibt bis zu 25 Ergebnisse zurück (2 API-Aufrufe à max. 20 Treffer).
    """
    results = []
    per_page = 20
    country = region.split("-")[1].upper() if "-" in region else "DE"

    for offset in range(0, MAX_SEARCH_RESULTS, per_page):
        count = min(per_page, MAX_SEARCH_RESULTS - offset)
        params = urllib.parse.urlencode({
            "q":       query,
            "count":   count,
            "offset":  offset,
            "country": country,
        })
        url = f"https://api.search.brave.com/res/v1/web/search?{params}"
        req = urllib.request.Request(url, headers={
            "Accept":        "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": args.api_key,
        })
        with _make_opener().open(req, timeout=10) as resp:
            data = json.loads(resp.read())

        web_results = data.get("web", {}).get("results", [])
        for item in web_results:
            results.append({
                "title": item.get("title", ""),
                "href":  item.get("url", ""),
                "body":  item.get("description", ""),
            })

        if len(web_results) < count:
            break   # keine weiteren Seiten verfügbar

    return results


SEARCH_BACKENDS = {
    "duckduckgo": _search_duckduckgo,
    "google":     _search_google,
    "brave":      _search_brave,
}


# ── MCP-Tool ──────────────────────────────────────────────────────────────────

@mcp.tool()
def web_search(query: str, region: str = "de-de") -> str:
    """
    Führt eine Websuche durch und gibt die ersten 25 Ergebnisse zurück.
    Nutze dieses Tool wenn der Nutzer 'recherchiere', 'suche' oder
    'mache eine Websuche' sagt, oder wenn aktuelle Informationen benötigt werden.

    Args:
        query:  Der Suchbegriff
        region: Regionscode, z.B. 'de-de' für Deutschland, 'en-us' für USA
    """
    label = PROVIDER_LABELS[args.provider]
    print(f"[MCP] web_search ({label}): query={query!r}, region={region!r}", flush=True)
    try:
        results = SEARCH_BACKENDS[args.provider](query, region)

        if not results:
            return f"Keine Suchergebnisse für '{query}' gefunden."

        print(f"[MCP] {len(results)} Ergebnisse gefunden.", flush=True)

        lines = [f"{label}-Suchergebnisse für \"{query}\" ({len(results)} Treffer):\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Kein Titel")
            url   = r.get("href", "")
            body  = r.get("body", "")
            lines.append(f"Quelle [{i}]: {title}")
            lines.append(f"URL: {url}")
            if body:
                lines.append(f"Zusammenfassung: {body}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"Fehler bei der {label}-Suche: {e}"


# ── Start ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "?.?.?.?"

    label = PROVIDER_LABELS[args.provider]
    print(f"{label} MCP-Server läuft auf Port {args.port}")
    print(f"  Lokal:    http://localhost:{args.port}/mcp")
    print(f"  Netzwerk: http://{local_ip}:{args.port}/mcp")
    if PROXY_URL:
        source = "--proxy" if args.proxy else "SEARCH_PROXY"
        print(f"  Proxy:    {PROXY_URL}  (Quelle: {source})")
        if _SYS_NO_PROXY:
            print(f"  no_proxy: {_SYS_NO_PROXY}")
    elif _SYS_HTTPS_PROXY or _SYS_HTTP_PROXY:
        print(f"  Proxy:    (Systemvariable)")
        if _SYS_HTTP_PROXY:
            print(f"            http_proxy  = {_SYS_HTTP_PROXY}")
        if _SYS_HTTPS_PROXY:
            print(f"            https_proxy = {_SYS_HTTPS_PROXY}")
        if _SYS_NO_PROXY:
            print(f"            no_proxy    = {_SYS_NO_PROXY}")
    else:
        print("  Proxy:    keiner")
    print("Verbinde in llama.cpp WebUI mit der Netzwerk-URL als MCP-Server.")
    print("Strg+C zum Beenden.\n")

    app = mcp.streamable_http_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    uvicorn.run(app, host=args.host, port=args.port)

"""
DuckDuckGo MCP-Server für llama.cpp WebUI
Verbinde ihn in der llama.cpp WebUI über:
  http://<server-ip>:3001/mcp
"""

import argparse
import socket
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from ddgs import DDGS

# ── Konfiguration ────────────────────────────────────────────────────────────
DEFAULT_HOST       = "0.0.0.0"
DEFAULT_PORT       = 3001
MAX_SEARCH_RESULTS = 25
# ─────────────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="DuckDuckGo MCP-Server für llama.cpp")
parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host (default: {DEFAULT_HOST})")
parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
args = parser.parse_args()

INSTRUCTIONS = """
Du hast Zugriff auf das Tool `web_search`, mit dem du aktuelle Informationen aus dem Internet abrufen kannst.

Nutze `web_search` IMMER in folgenden Situationen:
- Der Nutzer fragt nach aktuellen Ereignissen, Nachrichten oder Entwicklungen
- Der Nutzer fragt nach Preisen, Kursen, Wetterdaten oder anderen sich ändernden Informationen
- Dein Trainingswissen könnte veraltet sein (älter als 1-2 Jahre)
- Du bist dir nicht sicher, ob deine gespeicherten Informationen noch korrekt sind
- Der Nutzer sagt etwas wie: "suche", "such", "google", "recherchiere", "finde heraus", "was ist aktuell", "neueste", "aktuelle", "heutige"
- Der Nutzer stellt eine Frage, auf die du keine zuverlässige Antwort aus deinem Training geben kannst

Nutze `web_search` NICHT bei:
- Allgemeinen Wissensfragen zu stabilen Fakten (Mathematik, Grammatik, Programmierkonzepte)
- Aufgaben wie Texte schreiben, Code erklären oder umformulieren

Führe die Suche immer zuerst durch, bevor du antwortest, wenn einer der obigen Punkte zutrifft.
"""

mcp = FastMCP(
    "DuckDuckGo Websuche",
    instructions=INSTRUCTIONS,
    host=args.host,
    port=args.port,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


@mcp.tool()
def web_search(query: str, region: str = "de-de") -> str:
    """
    Führt eine DuckDuckGo-Websuche durch und gibt die ersten 25 Ergebnisse zurück.
    Nutze dieses Tool wenn der Nutzer 'recherchiere', 'suche' oder
    'mache eine Websuche' sagt, oder wenn aktuelle Informationen benötigt werden.

    Args:
        query:  Der Suchbegriff
        region: Regionscode, z.B. 'de-de' für Deutschland, 'en-us' für USA
    """
    print(f"[MCP] web_search aufgerufen: query={query!r}, region={region!r}", flush=True)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                region=region,
                safesearch="moderate",
                max_results=MAX_SEARCH_RESULTS
            ))

        if not results:
            return f"Keine Suchergebnisse für '{query}' gefunden."

        print(f"[MCP] {len(results)} Ergebnisse gefunden.", flush=True)

        lines = [f"DuckDuckGo-Suchergebnisse für \"{query}\" ({len(results)} Treffer):\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Kein Titel")
            url   = r.get("href", "")
            body  = r.get("body", "")
            lines.append(f"[{i}] {title}")
            lines.append(f"    URL: {url}")
            if body:
                lines.append(f"    {body}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"Fehler bei der DuckDuckGo-Suche: {e}"


if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "?.?.?.?"

    print(f"DuckDuckGo MCP-Server läuft auf Port {args.port}")
    print(f"  Lokal:   http://localhost:{args.port}/mcp")
    print(f"  Netzwerk: http://{local_ip}:{args.port}/mcp")
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

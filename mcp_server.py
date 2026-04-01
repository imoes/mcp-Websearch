"""
DuckDuckGo MCP-Server für llama.cpp WebUI
Verbinde ihn in der llama.cpp WebUI über:
  http://127.0.0.1:3001/mcp
"""

import argparse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from duckduckgo_search import DDGS

# ── Konfiguration ────────────────────────────────────────────────────────────
DEFAULT_HOST       = "127.0.0.1"
DEFAULT_PORT       = 3001
MAX_SEARCH_RESULTS = 25
# ─────────────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="DuckDuckGo MCP-Server für llama.cpp")
parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host (default: {DEFAULT_HOST})")
parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
args = parser.parse_args()

mcp = FastMCP(
    "DuckDuckGo Websuche",
    host=args.host,
    port=args.port,
    transport_security=TransportSecuritySettings(
        allowed_hosts=["localhost", "127.0.0.1", f"localhost:{args.port}", f"{args.host}:{args.port}"],
        allowed_origins=["http://localhost", "http://127.0.0.1", f"http://{args.host}:{args.port}"],
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
                keywords=query,
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
    print(f"DuckDuckGo MCP-Server startet auf http://{args.host}:{args.port}/mcp")
    print("Verbinde in llama.cpp WebUI mit dieser URL als MCP-Server.")
    print("Strg+C zum Beenden.\n")

    mcp.run(transport="streamable-http")

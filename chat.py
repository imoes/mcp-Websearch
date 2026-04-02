"""
llama.cpp Chat-Client mit DuckDuckGo Function Calling
Startet automatisch eine Websuche bei Begriffen wie:
  "recherchiere", "mache eine Websuche", "suche im Internet"
"""

import json
import sys
from openai import OpenAI
from duckduckgo_search import DDGS

# ── Konfiguration ────────────────────────────────────────────────────────────
LLAMA_SERVER_URL = "http://127.0.0.1:8080/v1"
API_KEY          = "not-needed"          # llama-server braucht keinen echten Key
MODEL_NAME       = "local-model"         # beliebiger Name, llama-server ignoriert ihn
MAX_SEARCH_RESULTS = 25
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Du bist ein hilfreicher Assistent mit Zugriff auf das Tool `web_search`.

Wann du `web_search` aufrufen MUSST:
- Der Nutzer sagt "recherchiere [Thema]"
- Der Nutzer sagt "mache eine Websuche zu [Thema]"
- Der Nutzer sagt "suche im Internet nach [Thema]"
- Der Nutzer sagt "suche nach [Thema]"
- Der Nutzer fragt nach aktuellen Ereignissen, Preisen oder Neuigkeiten
- Dein Wissen zu einem Thema könnte veraltet sein (nach August 2024)

Wann du NICHT suchen musst:
- Allgemeine Wissensfragen, die sich nicht ändern
- Mathematik, Logik, Programmierkonzepte
- Kreative Aufgaben wie Texte schreiben

Nach einer Websuche MUSST du folgendes Format einhalten:
1. Setze im Fließtext Fußnoten in eckigen Klammern [1], [2], ... direkt nach der jeweiligen Information
2. Jede Fußnotennummer entspricht der "Quelle [N]"-Nummer aus den Suchergebnissen
3. Verwende nur Quellen, die du tatsächlich zitierst — nicht alle 25 auflisten
4. Schreibe am Ende deiner Antwort einen Abschnitt "**Quellen:**" mit den zitierten Quellen als Markdown-Links:

   **Quellen:**
   [1] [Titel der Seite](https://url.example.com)
   [2] [Titel der Seite](https://url.example.com)

Trenne deutlich zwischen allgemeinem Wissen und den Suchergebnissen."""

TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Führt eine DuckDuckGo-Websuche durch und gibt die ersten 25 Ergebnisse zurück. "
                "Verwende dieses Tool bei Suchanfragen und Fragen zu aktuellen Informationen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Der Suchbegriff, nach dem gesucht werden soll"
                    },
                    "region": {
                        "type": "string",
                        "description": "Region für Suchergebnisse, z.B. 'de-de' für Deutschland",
                        "default": "de-de"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


def duckduckgo_search(query: str, region: str = "de-de") -> str:
    """Führt eine DuckDuckGo-Suche durch und gibt formatierte Ergebnisse zurück."""
    print(f"\n[Websuche] Suche nach: \"{query}\" ...", flush=True)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                keywords=query,
                region=region,
                safesearch="moderate",
                max_results=MAX_SEARCH_RESULTS
            ))

        if not results:
            return "Keine Suchergebnisse gefunden."

        print(f"[Websuche] {len(results)} Ergebnisse gefunden.\n", flush=True)

        formatted = f"DuckDuckGo-Suchergebnisse für \"{query}\" ({len(results)} Ergebnisse):\n\n"
        for i, result in enumerate(results, 1):
            title = result.get("title", "Kein Titel")
            url   = result.get("href", "")
            body  = result.get("body", "Keine Beschreibung")
            formatted += f"Quelle [{i}]: {title}\n"
            formatted += f"URL: {url}\n"
            formatted += f"Zusammenfassung: {body}\n\n"

        return formatted

    except Exception as e:
        return f"Fehler bei der Websuche: {e}"


def process_tool_call(tool_name: str, tool_args: dict) -> str:
    """Führt den vom Modell angeforderten Tool-Call aus."""
    if tool_name == "web_search":
        query  = tool_args.get("query", "")
        region = tool_args.get("region", "de-de")
        return duckduckgo_search(query, region)
    return f"Unbekanntes Tool: {tool_name}"


def chat_loop():
    """Haupt-Chat-Schleife mit Tool-Calling-Unterstützung."""
    client = OpenAI(base_url=LLAMA_SERVER_URL, api_key=API_KEY)

    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    print("=" * 60)
    print("  llama.cpp Chat mit DuckDuckGo Websuche")
    print("=" * 60)
    print("Befehle: 'exit' oder 'quit' zum Beenden")
    print("Tipp: Sage 'recherchiere [Thema]' für eine Websuche")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("Du: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBis zum nächsten Mal!")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "beenden"):
            print("Bis zum nächsten Mal!")
            sys.exit(0)

        conversation.append({"role": "user", "content": user_input})

        # ── Schleife: Modell kann mehrere Tool-Calls hintereinander machen ──
        while True:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=conversation,
                tools=TOOL_DEFINITION,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=2048
            )

            message = response.choices[0].message

            # Kein Tool-Call → finale Antwort ausgeben
            if not message.tool_calls:
                answer = message.content or ""
                print(f"\nAssistent: {answer}\n")
                conversation.append({"role": "assistant", "content": answer})
                break

            # Tool-Call(s) verarbeiten
            # Assistent-Nachricht mit Tool-Calls zur History hinzufügen
            conversation.append(message)

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                tool_result = process_tool_call(tool_name, tool_args)

                # Ergebnis zur Konversation hinzufügen
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })

            # Nächste Iteration: Modell formuliert Antwort auf Basis der Ergebnisse


if __name__ == "__main__":
    chat_loop()

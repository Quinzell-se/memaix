"""Genererar setup-complete.html efter en lyckad make init."""
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

VERIFIED_DATE = "2026-06-30"

_CLIENTS = [
    {
        "id": "claude",
        "name": "Claude",
        "logo": "🤖",
        "plan": "Pro ($20/mån)",
        "oauth": True,
        "steps": [
            "Gå till <strong>claude.ai</strong> &rarr; ditt namn uppe till höger &rarr; <strong>Settings</strong>.",
            "Välj fliken <strong>Connectors</strong>.",
            "Klicka <strong>Add custom connector</strong>.",
            "Klistra in din connector-URL (se ovan) och klicka <strong>Connect</strong>.",
            "Webbläsaren öppnar Memaix inloggning &rarr; logga in med ditt lösenord &rarr; klicka Godkänn.",
            "Konnektorn visas som <em>Connected</em> ✓. Synkas automatiskt till iOS och desktop.",
        ],
        "note": "Prova: skriv <em>\"kör whoami i Memaix\"</em> i en ny konversation.",
    },
    {
        "id": "mistral",
        "name": "Mistral Le Chat",
        "logo": "🌊",
        "plan": "Free (räcker)",
        "oauth": True,
        "steps": [
            "Gå till <strong>chat.mistral.ai</strong> &rarr; Settings &rarr; <strong>Connectors</strong>.",
            "Klicka <strong>Add connector</strong> &rarr; välj <em>Custom MCP</em>.",
            "Ange connector-URL (se ovan) &rarr; <strong>Connect</strong>.",
            "OAuth-flöde öppnas &rarr; logga in på din Memaix &rarr; klart.",
        ],
        "note": "Bra för att verifiera att konnektorn fungerar utan att betala för Pro.",
    },
    {
        "id": "chatgpt",
        "name": "ChatGPT",
        "logo": "💬",
        "plan": "Plus ($20/mån)",
        "oauth": True,
        "steps": [
            "Gå till <strong>chatgpt.com</strong> &rarr; Settings &rarr; <strong>Connectors</strong> (eller Tools).",
            "Klicka <strong>Add</strong> &rarr; välj <em>Custom MCP server</em>.",
            "Ange connector-URL (se ovan). Välj <strong>OAuth</strong> som autentiseringsmetod.",
            "Följ OAuth-flödet &rarr; logga in på din Memaix.",
        ],
        "note": "UI:t varierar med plan och region. Kontrollera OpenAIs support-sidor om stegen ser annorlunda ut.",
    },
    {
        "id": "perplexity",
        "name": "Perplexity",
        "logo": "🔍",
        "plan": "Pro ($20/mån)",
        "oauth": True,
        "steps": [
            "Gå till <strong>perplexity.ai</strong> &rarr; Settings &rarr; <strong>AI Tools</strong>.",
            "Lägg till MCP-server &rarr; ange connector-URL (se ovan).",
            "Följ OAuth-flödet.",
        ],
        "note": "Fokuserat på research-mode. Be Perplexity explicit använda Memaix-verktygen.",
    },
    {
        "id": "cursor",
        "name": "Cursor",
        "logo": "⌨️",
        "plan": "Hobby (gratis)",
        "oauth": False,
        "steps": [
            "Öppna Cursor &rarr; <strong>Settings &rarr; MCP &rarr; Add server</strong>.",
            "Välj <strong>HTTP</strong> &rarr; klistra in connector-URL (se ovan).",
            "Lägg till Bearer-token (generera via din Memaix-instans).",
        ],
        "note": "Cursor hanterar inte OAuth-flödet automatiskt — kräver manuell Bearer-token.",
    },
    {
        "id": "vscode",
        "name": "VS Code + Copilot",
        "logo": "🔷",
        "plan": "Copilot ($10/mån)",
        "oauth": False,
        "steps": [
            "Öppna Command Palette (<kbd>Cmd+Shift+P</kbd>) &rarr; <strong>GitHub Copilot: Add MCP Server</strong>.",
            "Välj <strong>HTTP</strong> &rarr; ange connector-URL (se ovan).",
            "Välj <strong>Bearer token</strong> &rarr; klistra in din Memaix-token.",
        ],
        "note": "Kräver Copilot-tillägg v1.250 eller nyare.",
    },
]


def _client_html(c: dict, url: str) -> str:
    steps_html = "\n".join(f"<li>{s}</li>" for s in c["steps"])
    auth_badge = (
        '<span class="badge badge-oauth">OAuth</span>'
        if c["oauth"]
        else '<span class="badge badge-bearer">Bearer-token</span>'
    )
    note_html = f'<p class="note">💡 {c["note"]}</p>' if c.get("note") else ""
    return f"""
    <div class="client" id="{c['id']}">
      <div class="client-header">
        <span class="logo">{c['logo']}</span>
        <div>
          <strong>{c['name']}</strong>
          <span class="plan">Lägsta plan: {c['plan']}</span>
        </div>
        {auth_badge}
      </div>
      <ol>{steps_html}</ol>
      {note_html}
    </div>"""


def generate(public_url: str, admin_user: str, output_path: str) -> None:
    url = public_url.rstrip("/")
    clients_html = "\n".join(_client_html(c, url) for c in _CLIENTS)

    html = f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memaix — klar att använda</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #f8fafc;
          color: #1e293b; line-height: 1.6; padding: 2rem 1rem; }}
  .container {{ max-width: 780px; margin: 0 auto; }}
  .hero {{ background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
           color: white; border-radius: 16px; padding: 2.5rem; margin-bottom: 2rem; }}
  .hero h1 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: .5rem; }}
  .hero p {{ opacity: .9; margin-bottom: 1.5rem; }}
  .url-box {{ background: rgba(255,255,255,.15); border-radius: 8px; padding: 1rem 1.25rem;
              font-family: monospace; font-size: 1.1rem; display: flex;
              justify-content: space-between; align-items: center; gap: 1rem; }}
  .copy-btn {{ background: white; color: #4f46e5; border: none; border-radius: 6px;
               padding: .4rem .9rem; font-size: .85rem; font-weight: 600;
               cursor: pointer; white-space: nowrap; }}
  .copy-btn:active {{ opacity: .8; }}
  .caveat {{ background: #fef9c3; border: 1px solid #fde047; border-radius: 10px;
             padding: 1rem 1.25rem; margin-bottom: 2rem; font-size: .9rem; }}
  .caveat strong {{ color: #854d0e; }}
  h2 {{ font-size: 1.2rem; font-weight: 700; margin-bottom: 1rem; color: #334155; }}
  .client {{ background: white; border-radius: 12px; padding: 1.5rem;
             margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .client-header {{ display: flex; align-items: center; gap: .75rem; margin-bottom: 1rem;
                    flex-wrap: wrap; }}
  .logo {{ font-size: 1.6rem; }}
  .plan {{ display: block; font-size: .8rem; color: #64748b; }}
  .badge {{ margin-left: auto; padding: .25rem .6rem; border-radius: 20px;
            font-size: .75rem; font-weight: 600; }}
  .badge-oauth {{ background: #dcfce7; color: #166534; }}
  .badge-bearer {{ background: #fef3c7; color: #92400e; }}
  ol {{ padding-left: 1.3rem; }}
  ol li {{ margin-bottom: .5rem; font-size: .95rem; }}
  .note {{ margin-top: 1rem; font-size: .88rem; color: #475569;
           background: #f1f5f9; padding: .75rem 1rem; border-radius: 8px; }}
  kbd {{ background: #e2e8f0; border-radius: 4px; padding: .1rem .35rem;
         font-family: monospace; font-size: .85em; }}
  .footer {{ text-align: center; font-size: .82rem; color: #94a3b8; margin-top: 2.5rem; }}
  .footer a {{ color: #6366f1; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">

  <div class="hero">
    <h1>✓ Memaix är uppe!</h1>
    <p>Din connector-URL — klistra in den i din AI-tjänst:</p>
    <div class="url-box">
      <span id="url">{url}</span>
      <button class="copy-btn" onclick="navigator.clipboard.writeText('{url}');this.textContent='Kopierad!'">Kopiera</button>
    </div>
  </div>

  <div class="caveat">
    <strong>⚠ Instruktionerna nedan är verifierade {VERIFIED_DATE}.</strong>
    AI-tjänsternas gränssnitt uppdateras löpande — stegen kan se annorlunda ut.
    Kontrollera tjänstens officiella dokumentation om något inte stämmer.
  </div>

  <h2>Koppla in din AI</h2>
  {clients_html}

  <div class="footer">
    <p>Inloggad som <strong>{admin_user}</strong> &middot;
       <a href="{url}/health">Hälsostatus</a> &middot;
       Kör <code>make doctor</code> om något inte funkar.</p>
    <p style="margin-top:.5rem">Memaix &middot; AGPL-3.0 &middot;
       <a href="docs/AI-CLIENTS.md">Fullständig klientdokumentation</a></p>
  </div>

</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

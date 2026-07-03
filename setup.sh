#!/bin/sh
# Memaix setup — starta, öppna webbläsaren, klart.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Kör:  ./setup.sh
# Wizarden binder bara 127.0.0.1. På en molnserver (headless): kör skriptet
# där, och på din egen dator:  ssh -L 8765:localhost:8765 din-server
# — öppna sedan länken lokalt. Token krävs; ingen annan kommer åt ytan.

set -eu
cd "$(dirname "$0")"
PORT="${MEMAIX_SETUP_PORT:-8765}"

command -v docker >/dev/null 2>&1 || {
  echo "✗ Docker krävs (enda beroendet). Installera: https://docs.docker.com/get-docker/"; exit 1; }

TOKEN="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
URL="http://127.0.0.1:${PORT}/?token=${TOKEN}"

echo ""
echo "  Memaix setup startar …"
echo ""
echo "  Öppna i din webbläsare:"
echo ""
echo "    ${URL}"
echo ""
if [ -z "${SSH_CONNECTION:-}" ] && [ -z "${SSH_TTY:-}" ]; then
  (command -v open >/dev/null && open "$URL") || \
  (command -v xdg-open >/dev/null && xdg-open "$URL") || true
else
  echo "  (Fjärrserver upptäckt — kör på din egen dator:"
  echo "     ssh -L ${PORT}:localhost:${PORT} $(hostname)"
  echo "   och öppna sedan länken ovan lokalt.)"
  echo ""
fi

# Wizarden: värd-python om det finns, annars i container (bara Docker krävs).
if command -v python3 >/dev/null 2>&1; then
  python3 scripts/setup_web.py --port "$PORT" --token "$TOKEN"
else
  docker run --rm -v "$(pwd)":/repo -w /repo -p "127.0.0.1:${PORT}:${PORT}" \
    python:3-alpine python scripts/setup_web.py --port "$PORT" --token "$TOKEN" --container
fi

[ -f .setup-result.json ] || { echo "✗ Ingen config skriven — avbrutet."; exit 1; }
TRACK="$(sed -n 's/.*"track": *\([0-9]*\).*/\1/p' .setup-result.json)"
TUNNEL="$(sed -n 's/.*"tunnel_provider": *"\([^"]*\)".*/\1/p' .setup-result.json)"

if [ "$TRACK" = "1" ]; then
  echo ""
  echo "  Trial-läge klart. Starta lokalt:  make up"
  echo "  Anslut Claude Desktop som stdio-MCP: se docs/AI-CLIENTS.md"
else
  echo ""
  echo "  Reser stacken …"
  PROFILES="--profile hydra"
  [ "$TUNNEL" = "cloudflare" ] && PROFILES="$PROFILES --profile tunnel"
  # shellcheck disable=SC2086
  docker compose $PROFILES up -d
  echo "  Kör hälsokontroll …"
  if command -v python3 >/dev/null 2>&1; then
    python3 scripts/bootstrap.py --doctor
  else
    docker run --rm --network host -v "$(pwd)":/repo -w /repo \
      python:3-alpine sh -c "pip -q install pyyaml && python scripts/bootstrap.py --doctor"
  fi
fi
echo ""
echo "  Klart! Nästa steg: docs/AI-CLIENTS.md (koppla din AI)."

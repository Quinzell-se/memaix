#!/usr/bin/env sh
# Memaix auto-installer.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Inspektera gärna detta skript innan du kör det — det är öppen källkod och gör inget dolt.
#
# Användning:
#   curl -fsSL https://get.memaix.example/install.sh | sh
#   (eller: ladda ner, läs igenom, kör — rekommenderas)
#
# Oövervakad (leverantör/headless/CI):
#   curl -fsSL https://get.memaix.example/install.sh | MEMAIX_PROFILE=trial sh -s -- --yes
#
# Miljövariabler: MEMAIX_REPO, MEMAIX_DIR, MEMAIX_PROFILE, MEMAIX_DOMAIN

set -eu

REPO="${MEMAIX_REPO:-https://github.com/CHANGE-ME/memaix.git}"
DIR="${MEMAIX_DIR:-memaix}"
UNATTENDED=0
[ "${1:-}" = "--yes" ] && UNATTENDED=1

echo "▸ Memaix-installer"

# 1. Förkontroll: Docker är enda förkunskapen (allt annat är containeriserat).
if ! command -v docker >/dev/null 2>&1; then
  echo "✗ Docker krävs men saknas. Installera Docker och kör igen:"
  echo "  https://docs.docker.com/get-docker/"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "✗ Docker Compose v2 krävs (ingår i moderna Docker-versioner)."
  exit 1
fi

# 2. Hämta koden (grund clone).
if [ ! -d "$DIR" ]; then
  echo "▸ Hämtar Memaix → $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi
cd "$DIR"

# 3. Setup — wizarden genererar all config + hemligheter.
if [ "$UNATTENDED" = "1" ]; then
  echo "▸ Oövervakad setup (profil: ${MEMAIX_PROFILE:-trial})"
  python3 scripts/bootstrap.py --init --yes
else
  make init
fi

# 4. Kör + verifiera.
make up
make doctor

echo "✓ Klart. Se utskriften ovan för hur du kopplar in din AI."

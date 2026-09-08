#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Container-rökprov: bygg imagen vi faktiskt shippar och kör kärnlöftet i den,
# i båda ägarskapsfallen.
#
# Fram till nu byggde CI aldrig imagen. Dockerfile och docker-compose.yml var
# otestade artefakter, och den enda gången de kördes skarpt var i produktion.
# Det kostade oss ett kärnlöfte som aldrig levererat en dag: containern körde
# som root mot bind-mounts ägda av värden, git vägrade, koden teg.
#
# Provet kör två gånger mot SAMMA vault, i den ordningen med flit:
#   1. friendly -- containerns uid äger vaulten. Skrivning ska ge en hash git
#      kan slå upp, historiken ska se den.
#   2. hostile  -- ett annat uid mot den nu befintliga vaulten. Det är exakt
#      produktionsformen (ett valv initierat av en ägare, opererat av en
#      annan), och det ska braka högljutt.
#
# Kör lokalt med: scripts/container-smoke.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO="$PWD"
IMAGE="memaix/gateway:smoke"

OWNER_UID="$(id -u)"
OWNER_GID="$(id -g)"
# Vilket uid som helst som inte är vårt eget. Poängen är skillnaden, inte talet.
if [ "$OWNER_UID" -eq 1000 ]; then OTHER_UID=1001; else OTHER_UID=1000; fi

WORK="$(mktemp -d)"
cleanup() {
  # Den fientliga körningen kan lämna filer ägda av OTHER_UID. Städa inifrån
  # en container som root, annars failar rm och maskerar provets utfall.
  docker run --rm -v "$WORK:/w" --user 0:0 "$IMAGE" rm -rf /w/vaults /w/config 2>/dev/null || true
  rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

echo "== Bygger $IMAGE =="
docker build -t "$IMAGE" "$REPO/gateway"

mkdir -p "$WORK/vaults/smoke" "$WORK/config"
cp "$REPO/scripts/container-smoke/acl.yaml" "$WORK/config/acl.yaml"
# mktemp ger 700. Utan läsbarhet nedåt hade den fientliga körningen fallit på
# att den inte kan gå in i katalogen, inte på ägarskapet -- rätt utfall av fel
# skäl, vilket är ett prov som ljuger.
chmod -R a+rX "$WORK"

run_smoke() {
  local label="$1" uid="$2"
  docker run --rm \
    --user "$uid:$OWNER_GID" \
    -v "$WORK/config:/app/config" \
    -v "$WORK/vaults:/srv/vaults" \
    -v "$REPO/scripts/container-smoke/smoke.py:/smoke.py:ro" \
    "$IMAGE" python /smoke.py "$label"
}

echo
echo "== 1/2 friendly: containern kör som $OWNER_UID, äger vaulten =="
run_smoke friendly "$OWNER_UID"

echo
echo "== 2/2 hostile: containern kör som $OTHER_UID mot samma vault =="
# Skrivbart för alla, men .git ägs fortfarande av friendly-körningens uid.
# Det är produktionsformen exakt: containern körde som root och kunde skriva
# vad som helst -- SQLite-indexet fungerade -- medan git ensamt vägrade på
# ägarskapet. Utan det här steget dör provet redan på "readonly database" och
# når aldrig git, vilket är rätt utfall av fel skäl: det hade inte fångat en
# regression där git blir tyst igen.
chmod -R a+rwX "$WORK/vaults"
run_smoke hostile "$OTHER_UID"

echo
echo "== Rökprovet gick igenom: imagen bygger, monteringarna bär, git levererar,"
echo "   och fel ägarskap hörs i stället för att sväljas. =="

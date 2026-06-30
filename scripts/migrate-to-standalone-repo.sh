#!/usr/bin/env bash
# Migrera memaix/ från project-a-se/jimlov-se till ett eget, fristående repo — med bevarad historik.
#
# KÖRS FRÅN EN FULL KLON av jimlov-se (lokala bygg-sessionen), INTE från den scopade molnsessionen.
# Skapa det nya TOMMA repot på GitHub först (t.ex. github.com/memaix/memaix) och sätt NEW_REMOTE_URL.
#
#   NEW_REMOTE_URL=git@github.com:memaix/memaix.git ./migrate-to-standalone-repo.sh
#
set -euo pipefail

SRC_REMOTE="${SRC_REMOTE:-origin}"
BASE_BRANCH="${BASE_BRANCH:-main}"
PREFIX="memaix"
WORK="${WORK:-../memaix-standalone}"
: "${NEW_REMOTE_URL:?Sätt NEW_REMOTE_URL till det nya tomma repot, t.ex. git@github.com:memaix/memaix.git}"

echo "==> 1/5 Uppdaterar $BASE_BRANCH"
git checkout "$BASE_BRANCH"
git pull "$SRC_REMOTE" "$BASE_BRANCH"

echo "==> 2/5 Subtree-split av $PREFIX/ (bevarar bara commits som rörde memaix/)"
git branch -D memaix-export 2>/dev/null || true
git subtree split --prefix="$PREFIX" -b memaix-export

echo "==> 3/5 Klonar ut split-historiken (single-branch → ingen annan historik följer med)"
rm -rf "$WORK"
git clone --single-branch --branch memaix-export . "$WORK"
cd "$WORK"
git checkout -B "$BASE_BRANCH"
git branch -D memaix-export 2>/dev/null || true

echo "==> Verifierar att rot-scaffold finns"
for f in LICENSE NOTICE CONTRIBUTING.md AGENTS.md README.md .github/workflows/ci.yml; do
  test -e "$f" || { echo "SAKNAS i roten: $f"; exit 1; }
done
echo "    OK — licens/CI/scaffold ligger i roten"

echo "==> Integritets-sanity: inga privata referenser fick följa med"
if git grep -niE 'GAR00J|marvel r|negotiator' -- . >/dev/null 2>&1; then
  echo "VARNING: privata referenser hittade — AVBRYT och granska"; exit 1
fi
echo "    OK — inget privat"

echo "==> 4/5 Pekar om origin → $NEW_REMOTE_URL och pushar"
git remote remove origin 2>/dev/null || true
git remote add origin "$NEW_REMOTE_URL"
git push -u origin "$BASE_BRANCH"

cat <<'NEXT'

==> 5/5 KLART (pushat). Manuella efter-steg:
  [ ] GitHub: aktivera Actions på nya repot (Settings -> Actions -> Allow all) -> ci.yml kör docs-check + py_compile + SBOM.
  [ ] Uppdatera live-deployens git-remote (mcp.example.com) till nya repot.
  [ ] I jimlov-se: ta bort memaix/ (eller ersatt med README-pekare) i en egen PR.
  [ ] HANDOFF.md/AGENTS.md i nya repot: uppdatera repo-/branch-referenser.
  [ ] Granska en sista gang att inget privat foljt med, satt sedan repo publikt + topics + beskrivning.
  [ ] (Valfritt) branch protection pa main for PR-gate.
NEXT

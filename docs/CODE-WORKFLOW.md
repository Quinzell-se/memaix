# Kod-arbetsflöde — backlog → kod → merge (forge-agnostiskt)

Hur ett backlog-item blir mergad kod, och hur Memaix hanterar in/ut-checkning utan att återuppfinna
versionshantering.

## Princip: koordinera, återuppfinn inte git
Memaix = koordinations-/minneslagret. **Git-forgen** (GitHub/GitLab/Forgejo) = kodens
*system-of-record*. Memaix bygger **inte** VCS/merge — den **länkar** backlog-item ↔ branch/PR, **synkar
status**, och låter PMA:n spegla kodprogress in i planen. Check-in/-ut/merge sker i forgen, enligt
teamets regler.

## Livscykeln
1. Backlog-item `QB-0042` → owner sätter `approved`/`in-dev`.
2. **`code_branch`** → branch `QB-0042-csv-export` i projektets repo.
3. Utvecklaren bygger med **sin egen kod-AI** (Claude Code/Cursor/… — BYO, som allt annat), committar.
4. **`code_pr_open`** → PR **länkad till item** (item ↔ PR åt båda håll).
5. Review + CI i forgen (Forgejo/Gitea Actions kör **samma workflow-YAML som GitHub**; GitLab CI; GitHub Actions).
6. **Merge i forgen** (PR-knapp/API), enligt branch protection + review-regler. PMA **nudgar** (CI röd,
   review väntar) men forgen **enforcar**.
7. Webhook *PR merged* → item → `done` automatiskt (events, ARCHITECTURE #17).

## Forge-agnostisk adapter (som mejl/kalender/filer)
Ett `code`-resurslager per projekt, via forgens API:
| Forge | Roll |
|---|---|
| **GitHub** (moln) | default för dem som redan kör det |
| **GitLab CE** (self-host) | full DevOps i en låda (tyngre: 4 GB+, Postgres/Redis) |
| **Forgejo / Gitea** (self-host) | **rekommenderat self-host** — lätt (SQLite, single binary), AGPL (Forgejo), CI = GitHub-workflow-YAML |
| plain git/SSH | minimalist; ingen PR/issue-UI |

**Bundlad Forgejo** kan ingå i compose (som Nextcloud) för self-host-everything-kunden.

## Verktyg (`code_*`)
| Verktyg | Roll |
|---|---|
| `code_branch(project, item)` | collaborator |
| `code_pr_open(project, item, branch, title?)` | collaborator |
| `code_link(project, item, pr)` | collaborator |
| `code_status(project, item\|pr)` → CI / review / mergeable | reader |
| `code_merge(project, pr)` (endast om CI grön + review ok) | **owner/maintainer** |

## Statussync (webhooks, åt båda håll)
- PR öppnad → item `in-dev`; PR merged → item `done`; PR stängd → item tillbaka.
- Item visar PR-status i backloggen; **PMA räknar om beroenden/kritisk linje** när en uppgifts PR mergas.

## RBAC & säkerhet
- `code_merge` = owner/maintainer — **speglar forgens branch protection** (Memaix kringgår den aldrig).
- Forge-token i secret store; aldrig mot AI:n. Extern konsult: forge-access scopad till projektets repo.

## Honest poäng
Memaix gör koden **synlig och kopplad till planen** — inte ett nytt git. Utvecklarens kod-AI är **BYO**,
precis som allt annat: olika personer, olika AI:er, **samma projektminne + samma forge**.

## Acceptanskriterier
- [ ] Ett backlog-item ger en branch + länkad PR med ett kommando.
- [ ] PR-merge i forgen flyttar item → `done` automatiskt (webhook).
- [ ] Forge-agnostiskt: GitHub, GitLab CE, Forgejo/Gitea via samma adapter.
- [ ] Merge respekterar forgens branch protection/review; Memaix enforcar inte själv.
- [ ] PMA räknar om planen när en uppgifts PR mergas.

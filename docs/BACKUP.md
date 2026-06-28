# Backup & återställning

Vad som säkras, hur, och hur man återställer en Memaix-instans. Hör ihop med livscykeln
(`AUTO-INSTALLER.md` Fas E) och verifieras av `DOCTOR.md` efter restore.

## Vad ska säkras (och vad inte)

| Data | Var | Känslighet | Metod | Frekvens |
|---|---|---|---|---|
| **Vaults** (minne, backlog, PM) | SQLite + git-repon | medel (institutionell kunskap) | git-push till remote + restic | dagligen |
| **Config** (brand/memaix/acl) | `config/*.yaml` | låg–medel | restic | dagligen |
| **Hemligheter** (`.env`, token-store) | `.env`, krypterad token-store | **hög** | restic, krypterat | dagligen |
| **Nextcloud-data** (filer, kalender, kontakter) | NC data-dir + databas | hög | restic (+ maintenance mode/snapshot) | dagligen |
| **Mejl** | hos leverantören (Purelymail/MXroute/Gmail) | — | **leverantörens ansvar, inte Memaix** | — |
| Containrar/images | — | — | byggs om från compose, säkras ej | — |

> Kronjuvelen är **vaults** (kunskapen) + **token-store/hemligheter**. Mejl ligger kvar hos
> mejlleverantören och är inte Memaix att backa upp.

## Ansats

- **restic** (eller borg) till offsite objektlagring (S3 / Backblaze B2 / Wasabi) — **krypterat,
  deduplicerat, inkrementellt**. Ett verktyg täcker vaults + config + hemligheter + NC-data.
- **git-push av vaults** som extra, billigt och granulärt lager (varje commit → en remote).
- **Nextcloud:** för konsistent dump, kör maintenance mode eller volym-snapshot kring backupen
  (data-dir + DB-dump + `config.php`).

## Config (`config/backup.yaml`)
```yaml
backup:
  tool: restic                       # restic | borg | git-only
  repo: "s3:s3.eu-central.../memaix-acme"
  password_ref: BACKUP_KEY           # KUNDÄGD krypteringsnyckel (i .env)
  schedule: "daily 03:00"
  retention: { daily: 7, weekly: 4, monthly: 6 }
  include: [vaults, config, secrets, nextcloud-data]
  vault_git_remote: "git@backup.example.com:memaix-acme-vaults.git"
```

## Principer
- **3-2-1:** tre kopior, två medier, minst en offsite.
- **Krypterat i vila och transit; kundägd nyckel** — du som leverantör kan inte läsa kundens backup
  (linjerar med "kunden äger sin data").
- **Backupen innehåller hemligheter** → behandla den med samma skydd som token-store.
- **Automatiserat + schemalagt + verifierat** — en backup du aldrig testat återställa är ingen backup.
- **Retention-policy** så gammalt rensas och kostnaden hålls nere.

## Återställnings-runbook
1. Provisionera ren instans (compose upp, samma version).
2. Återställ **hemligheter + config** (restic restore → `.env`, `config/`).
3. Återställ **vaults** (restic eller `git clone` från `vault_git_remote`).
4. Återställ **Nextcloud** (data-dir + DB-dump, lämna maintenance mode).
5. Kör **`memaix doctor`** — grönt = återställningen lyckades.
6. Per-användar-OAuth: om token-store återställdes funkar kopplingarna; annars länkar användarna om
   (`auth_required`).

## Vad disaster recovery ser ut som
Instansen är **reproducerbar**: compose + images bygger om koden, backupen återför *datan*. Förlorad
maskin → ny maskin + restore + doctor grönt. Inget unikt sitter i containern.

## Kommandon
```
memaix backup            # kör backup nu
memaix backup --verify   # provåterställ till temp och kontrollera (regelbundet!)
memaix restore <snapshot># återställ angiven punkt
```

## Acceptanskriterier
- [ ] Vaults, config, hemligheter och NC-data säkras schemalagt och krypterat offsite.
- [ ] Krypteringsnyckeln är kundägd; leverantören kan inte läsa kundens backup.
- [ ] `memaix backup --verify` provåterställer och bekräftar integritet.
- [ ] Full restore på ren maskin ger `doctor` grönt.
- [ ] Retention-policy tillämpas; mejl exkluderas (leverantörens ansvar, dokumenterat).

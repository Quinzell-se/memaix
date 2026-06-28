# Uppdatering — `memaix update`

Hur en instans uppgraderas säkert: nya images, config-/data-migreringar, rollback och nedtid.
Hör ihop med `BACKUP.md` (backas alltid först) och `DOCTOR.md` (verifierar efteråt). Livscykel:
`AUTO-INSTALLER.md` Fas E.

## Princip
- **Backa först, alltid.** `update` kör `backup` innan något rörs; misslyckas backupen → avbryt.
- **Idempotent & additivt.** Migreringar lägger till, raderar inte data. Omkörning är säker.
- **Verifiera eller rulla tillbaka.** Doctor grön efter → klart. Röd → automatisk rollback.
- **Reproducerbart.** Kod kommer från versionsmärkta images; bara *datan* är unik.

## Versionering
- Produkten har en **semver** (t.ex. `1.4.0`). Images taggas per version.
- Config bär `schema_version`. Gatewayen vägrar starta om config-schemat är **nyare** än koden förstår.
- **Migreringar** är ordnade steg från nuvarande → mål, med applicerat-state registrerat.

```
migrations/
  0003_backlog_add_risk_field.py     # data: lägg fält i backlog-frontmatter
  0004_acl_split_resource_blocks.py  # config: migrera acl.yaml-form
```
Varje migrering är idempotent och bockar av sig i en statefil. Både **config-** och **vault-data**-
migreringar stöds.

## Flöde (runbook)
1. Läs nuvarande + målversion. `--dry-run` visar väntande migreringar utan att köra.
2. **Backup** (BACKUP.md) — avbryt om den fallerar.
3. Hämta nya images/kod.
4. Stoppa gateway kort (datavolymer behålls).
5. Kör väntande migreringar (config + vault), idempotent, registrera.
6. Starta nya containrar; kör **idempotent provisionering** (återskapar inte befintliga
   användare/hemligheter).
7. **Nextcloud:** `occ upgrade` om NC-imagen höjts (sekventiella major-steg — hoppa inte över versioner).
8. **Doctor.** Grön → klart. Röd → **rollback** (föregående images + restore från backup).
9. Vid fel: skicka `operator_alert` (SYSTEM-MAIL.md).

## Nedtid — ärligt
- Single-tenant, liten instans: en **kort omstart (sekunder)** är acceptabel. Tunneln visar en
  maintenance-sida under tiden.
- **Inte** äkta noll-nedtid i v1 (blue-green är overkill för en liten box). Noteras som framtida
  option om någon kund kräver det.

## Säkerhet & bakåtkompatibilitet
- Migreringar är additiva; aldrig destruktiva utan explicit, dokumenterat steg.
- Gatewayen läser **både gammalt och nytt** config-format under en övergångsversion där möjligt.
- Brytande ändringar flaggas i release notes och kräver `--allow-breaking`.
- Leverantör: testa uppdateringen på en **kopia** (restore till staging) före kundens produktion.

## Kommandon
```
memaix update              # till senaste
memaix update --to 1.4.0   # till specifik version
memaix update --dry-run    # visa väntande migreringar, kör inget
memaix rollback            # återgå till föregående version + backup
```

## Acceptanskriterier
- [ ] `update` backar upp innan något ändras och avbryter om backupen fallerar.
- [ ] Config- och vault-migreringar är ordnade, idempotenta och registrerade.
- [ ] Doctor körs efter; röd resultat utlöser automatisk rollback.
- [ ] `--dry-run` visar väntande migreringar utan att ändra något.
- [ ] Nextcloud-major-uppgraderingar körs sekventiellt, inte hoppvis.
- [ ] Nedtiden är en kort, kommunicerad omstart (maintenance-sida via tunneln).

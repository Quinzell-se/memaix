# Installation (självhostat)

## Krav
- En server du kontrollerar (egen maskin eller egen molnhosting).
- Docker + Docker Compose.
- En domän du styr över (för OAuth-issuer och connector-URL).
- Ett sätt att exponera endpointen publikt: Cloudflare-tunnel (rekommenderas) eller egen
  reverse proxy med TLS.
- Backends: en IMAP/SMTP-brevlåda, och CalDAV/WebDAV (t.ex. Nextcloud) om du vill ha
  kalender och filer.

## Steg

1. **Klona och konfigurera**
   ```bash
   git clone <ditt-memaix-repo> memaix && cd memaix
   cp .env.example .env
   cp config/brand.example.yaml  config/brand.yaml
   cp config/memaix.example.yaml config/memaix.yaml
   cp config/acl.example.yaml    config/acl.yaml
   ```

2. **Fyll i config**
   - `config/memaix.yaml` — din domän (`public_url`), tunnel, vaults_dir.
   - `config/acl.yaml` — användare, grants, projekt och deras backends.
   - `config/brand.yaml` — namn/branding (valfritt, default Memaix).
   - `.env` — OAuth-signeringsnyckel (`openssl rand -hex 32`) och backend-lösenord.

3. **Exponera publikt**
   - **Cloudflare-tunnel:** skapa en tunnel, peka hostname → `http://gateway:8080`, lägg
     `CLOUDFLARE_TUNNEL_TOKEN` i `.env`. **Lägg ingen Access framför** och **stäng av Bot Fight
     Mode** för hostnamnet (se SECURITY.md).
   - **Egen reverse proxy:** sätt `tunnel.provider: none` och terminera TLS själv (Caddy/nginx).

4. **Starta**
   ```bash
   docker compose --profile tunnel up -d         # + --profile nextcloud om du vill ha Nextcloud
   ```

5. **Seed-vaults**
   - Kopiera `vault-template/` till `vaults/` och initiera git-repon per projekt.
   - Fyll `shared/` (manual, om-filer, skrivstil) eller låt onboarding-intervjun göra det.

6. **Koppla in din AI** — se [AI-CLIENTS.md](AI-CLIENTS.md).

## Verifiera
- `whoami` via AI:n returnerar rätt användare + grants.
- En extern testanvändare når bara sitt projekt.
- `email_send` är avstängt; inga backend-lösenord syns mot AI:n.

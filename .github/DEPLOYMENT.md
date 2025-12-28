# Automatisk Deployment

Dette repoet bruker GitHub Actions for automatisk deployment til serveren når endringer pushes til `main`-branchen.

## Oppsett av GitHub Secrets

For at automatisk deployment skal fungere, må følgende secrets være satt opp i GitHub repository settings:

### Nødvendige Secrets

Gå til **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

1. **SSH_HOST**
   - Verdi: IP-adressen eller hostname til serveren (nrec)
   - Eksempel: `158.39.xxx.xxx` eller `nrec.example.com`

2. **SSH_USERNAME**
   - Verdi: Brukernavn for SSH-tilgang til serveren
   - Eksempel: `ubuntu` eller ditt brukernavn

3. **SSH_PRIVATE_KEY**
   - Verdi: Din private SSH-nøkkel for å koble til serveren
   - For å finne nøkkelen din:
     ```bash
     cat ~/.ssh/id_rsa
     # eller
     cat ~/.ssh/id_ed25519
     ```
   - Kopier hele innholdet inkludert `-----BEGIN` og `-----END` linjene

4. **SSH_PORT** (valgfri)
   - Verdi: SSH-port (standard er 22)
   - Kun nødvendig hvis serveren bruker en annen port

## Slik fungerer det

Når du pusher til `main`:

1. GitHub Actions SSH-er inn på serveren
2. Går til `backend`-mappen
3. Kjører `git pull origin main` for å hente nyeste kode
4. Stopper eksisterende Docker-containere med `docker compose down`
5. Bygger og starter containere på nytt med `docker compose up -d --build`
6. Viser de siste 50 linjene av loggene

## Manuell deployment

Du kan fortsatt deploye manuelt ved å:

```bash
ssh nrec
cd backend
git pull origin main
docker compose down && docker compose up -d --build
```

## Oppsett av n8n health check

For at n8n-statussjekken skal fungere, må du legge til n8n-tjenesten i `docker-compose.yml` på serveren:

```yaml
  n8n-api:
    build:
      context: .
      dockerfile: Dockerfile
    command: ["uvicorn", "apps.n8n.main:app", "--host", "0.0.0.0", "--port", "5004"]
    restart: unless-stopped
    expose:
      - "5004"
    environment:
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
    networks:
      - backend
```

Og legg til ruting i Caddyfile:

```
handle_path /n8n/* {
    reverse_proxy n8n-api:5004
}
```

## Feilsøking

Hvis deployment feiler:
- Sjekk Actions-fanen i GitHub for feilmeldinger
- Verifiser at alle secrets er riktig konfigurert
- Sjekk at SSH-nøkkelen har tilgang til serveren
- Sjekk at brukeren har rettigheter til å kjøre Docker-kommandoer

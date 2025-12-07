# 🎄 Julekalender Backend Guide

## Oversikt

Backenden kan nå lagre julekalenderdata i PostgreSQL-databasen og serve den til frontenden via API.

---

## 📊 Database Modell

### `calendar_days` tabell

| Kolonne | Type | Beskrivelse |
|---------|------|-------------|
| `id` | Integer | Primary key |
| `day` | Integer | Dag-nummer (1-24), unik |
| `type` | String | Type innhold (text, code, wordle, etc.) |
| `data` | JSON | Alt annet data for dagen |
| `created_at` | DateTime | Når raden ble opprettet |
| `updated_at` | DateTime | Når raden sist ble oppdatert |

---

## 🔌 API Endpoints

**⚠️ Alle endepunkter krever autentisering med X-API-Key header (unntatt /health)**

### 1. Hent alle dager

```http
GET /calendar/days
X-API-Key: your_api_key_here
```

**Response:**
```json
{
  "1": { "day": 1, "type": "text", "title": "Julehilsen", "body": "..." },
  "2": { "day": 2, "type": "code", "title": "Kodeluke", "starter": "..." },
  ...
}
```

**401 Error hvis uautentisert:**
```json
{
  "detail": "Invalid or missing API key"
}
```

### 2. Hent én spesifikk dag

```http
GET /calendar/days/1
X-API-Key: your_api_key_here
```

**Response:**
```json
{
  "day": 1,
  "type": "text",
  "title": "Julehilsen",
  "body": "En koselig melding her."
}
```

**401 Error hvis uautentisert:**
```json
{
  "detail": "Invalid or missing API key"
}
```

### 3. Seed database med data (én gang)

```http
POST /calendar/seed
Content-Type: application/json
X-API-Key: your_api_key_here

{
  "1": { "type": "text", "title": "Julehilsen", "body": "..." },
  "2": { "type": "code", ... },
  ...
}
```

**401 Error hvis uautentisert:**
```json
{
  "detail": "Invalid or missing API key"
}
```

---

## 🚀 Steg-for-steg: Migrer data fra JSON til backend

### Steg 1: Start backend lokalt

```bash
cd ~/Developer/backend
docker-compose up -d --build
```

### Steg 2: Seed databasen med JSON-data

**Metode A: Via curl**

```bash
curl -X POST http://localhost/calendar/seed \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d @path/to/your/calendar-data.json
```

**Metode B: Via API docs (enklest)**

1. Åpne http://localhost/docs
2. Finn `POST /calendar/seed`
3. Klikk "Try it out"
4. Lim inn JSON-dataen din
5. Klikk "Execute"

**Metode C: Via Python-script**

```python
import requests
import json

# Les JSON-fil
with open('calendar-data.json', 'r', encoding='utf-8') as f:
    calendar_data = json.load(f)

# Send til backend
response = requests.post(
    'http://localhost/calendar/seed',
    json=calendar_data
)

print(response.json())
# Output: {"message": "Successfully seeded 11 days", "days": 11}
```

### Steg 3: Verifiser at data er lagret

```bash
# Hent alle dager
curl -H "X-API-Key: your_api_key_here" http://localhost/calendar/days

# Hent dag 1
curl -H "X-API-Key: your_api_key_here" http://localhost/calendar/days/1
```

### Steg 4: Oppdater frontend

**Før (henter fra JSON-fil):**
```typescript
// calendar-data.json
import calendarData from './calendar-data.json';

const data = calendarData['1'];
```

**Etter (henter fra API):**
```typescript
// src/api/calendar.ts
export async function getCalendarDays() {
  const response = await fetch(`${API_BASE_URL}/calendar/days`, {
    headers: getHeaders(),
  });
  return response.json();
}

export async function getCalendarDay(dayNumber: number) {
  const response = await fetch(`${API_BASE_URL}/calendar/days/${dayNumber}`, {
    headers: getHeaders(),
  });
  return response.json();
}

// I komponenten din
import { getCalendarDays, getCalendarDay } from './api/calendar';

// Hent alle dager
const allDays = await getCalendarDays();
const dayOne = allDays['1'];

// Eller hent én dag
const dayOne = await getCalendarDay(1);
```

---

## 📝 Eksempel: React Hook

```typescript
// useCalendar.ts
import { useState, useEffect } from 'react';
import { getCalendarDays } from './api/calendar';

export function useCalendar() {
  const [days, setDays] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    async function fetchDays() {
      try {
        const data = await getCalendarDays();
        setDays(data);
      } catch (err) {
        setError(err as Error);
      } finally {
        setLoading(false);
      }
    }

    fetchDays();
  }, []);

  return { days, loading, error };
}

// I komponenten
function Calendar() {
  const { days, loading, error } = useCalendar();

  if (loading) return <div>Laster...</div>;
  if (error) return <div>Feil: {error.message}</div>;

  return (
    <div>
      {Object.entries(days).map(([dayNum, dayData]) => (
        <Day key={dayNum} data={dayData} />
      ))}
    </div>
  );
}
```

---

## 🔄 Oppdatere kalenderdata

Hvis du trenger å endre data senere:

1. **Oppdater JSON-filen**
2. **Kjør seed igjen** (overskriver eksisterende data):

```bash
curl -X POST http://localhost/calendar/seed \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d @calendar-data.json
```

---

## 🌐 Production Deployment

### På serveren (DigitalOcean)

```bash
# 1. SSH til serveren
ssh root@your-server-ip

# 2. Gå til backend-mappen
cd ~/backend

# 3. Pull siste endringer
git pull

# 4. Rebuild backend
docker-compose up -d --build

# 5. Seed databasen (bruk production URL)
curl -X POST https://api.vuhnger.dev/calendar/seed \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d @calendar-data.json
```

**OBS:** Husk å bruke API-nøkkel i production!

---

## 🔐 Sikkerhet

### API Key Autentisering

**✅ Allerede implementert!** Alle endepunkter (unntatt `/health`) er beskyttet med API key autentisering.

**Beskyttede endepunkter:**
- `GET /calendar/days` - Les alle dager (krever API key)
- `GET /calendar/days/{day_number}` - Les én dag (krever API key)
- `POST /calendar/seed` - Skriv/oppdater data (krever API key)

**Ubeskyttet endepunkt:**
- `GET /calendar/health` - Health check (ingen API key nødvendig)

**Slik bruker du API key:**

```bash
# Alle requests må inkludere X-API-Key header
curl -H "X-API-Key: your_secret_key" https://api.vuhnger.dev/calendar/days

# Uten API key får du 401 Unauthorized
curl https://api.vuhnger.dev/calendar/days
# {"detail": "Invalid or missing API key"}
```

**Sette opp API key:**
1. Generer sikker nøkkel: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Legg til i `.env`: `INTERNAL_API_KEY=generated_key_here`
3. Restart containere: `docker-compose restart`

---

## 📊 Database Management

### Backup kalenderdataen

```bash
# Eksporter kun calendar_days tabellen
docker-compose exec db pg_dump -U backend_user -d backend_db \
  -t calendar_days > calendar_backup.sql
```

### Restore fra backup

```bash
cat calendar_backup.sql | docker-compose exec -T db \
  psql -U backend_user -d backend_db
```

### Se data i databasen

```bash
# Åpne PostgreSQL shell
docker-compose exec db psql -U backend_user -d backend_db

# SQL kommandoer
SELECT * FROM calendar_days;
SELECT * FROM calendar_days WHERE day = 1;
SELECT day, type FROM calendar_days ORDER BY day;
\q  # exit
```

---

## 🎯 Testing

### Test alle endpoints

```bash
# Health check (ingen API key nødvendig)
curl http://localhost/calendar/health

# Hent alle dager (krever API key)
curl -H "X-API-Key: your_api_key_here" http://localhost/calendar/days | jq

# Hent dag 1 (krever API key)
curl -H "X-API-Key: your_api_key_here" http://localhost/calendar/days/1 | jq

# Test uten API key (skal feile med 401)
curl http://localhost/calendar/days
# Response: {"detail": "Invalid or missing API key"}

# Hent dag 25 (skal feile med 400)
curl -H "X-API-Key: your_api_key_here" http://localhost/calendar/days/25
# Response: {"detail": "Day must be between 1 and 24"}

# Hent dag som ikke finnes (skal feile med 404)
curl -H "X-API-Key: your_api_key_here" http://localhost/calendar/days/15
# Response: {"detail": "Day 15 not found"}
```

---

## 🐛 Troubleshooting

### Problem: "Table calendar_days doesn't exist"

**Løsning:** Restart backend (tabellen opprettes automatisk):

```bash
docker-compose restart calendar-api
```

### Problem: "Connection refused"

**Løsning:** Sjekk at backend kjører:

```bash
docker-compose ps
docker-compose logs calendar-api
```

### Problem: Seed gir feil

**Løsning:** Sjekk JSON-format:

```bash
# JSON må være valid og ha riktig struktur
{
  "1": { "type": "text", ... },  // ✓ Korrekt
  1: { "type": "text", ... }      // ✗ Feil (må være string)
}
```

---

**Last updated:** 2025-12-07

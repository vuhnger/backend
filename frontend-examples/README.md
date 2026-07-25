# Frontend Integration Examples

This directory contains example TypeScript/React files for integrating with the backend API.

## 📁 Files Overview

```
frontend-examples/
├── .env.example              # Environment configuration
├── src/
│   ├── api/
│   │   ├── types.ts         # TypeScript interfaces for API responses
│   │   └── calendar.ts      # Calendar API client functions
│   └── components/
│       └── HealthCheck.tsx  # Example React component
```

## 🚀 How to Use

### 1. Copy Files to Your Frontend Project

Copy these files to your React/Vite frontend project:

```bash
# From your frontend project root
cp -r ../backend/frontend-examples/src/api ./src/
cp -r ../backend/frontend-examples/src/components ./src/
cp ../backend/frontend-examples/.env.example ./.env
```

### 2. Configure Environment Variables

Edit `.env` in your frontend project:

```env
# For local development
VITE_API_BASE_URL=http://localhost

# For production
VITE_API_BASE_URL=https://api.vuhnger.dev
```

### 3. Use in Your React App

```tsx
import { HealthCheck } from './components/HealthCheck';

function App() {
  return (
    <div>
      <h1>My App</h1>
      <HealthCheck />
    </div>
  );
}
```

## 📚 API Client Pattern

All API calls follow this pattern:

```typescript
// 1. Define the response type in types.ts
export interface SomeResponse {
  data: string;
}

// 2. Create the API function in calendar.ts
export async function getSomething(): Promise<SomeResponse> {
  const response = await fetch(`${API_BASE_URL}/calendar/something`);
  if (!response.ok) throw new Error('Failed');
  return response.json();
}

// 3. Use in React components
const [data, setData] = useState<SomeResponse | null>(null);
useEffect(() => {
  getSomething().then(setData);
}, []);
```

## 🔒 Adding Authentication (STEP 5)

When API key authentication is added in STEP 5, update the fetch calls:

```typescript
export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/calendar/health`, {
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': import.meta.env.VITE_API_KEY, // Add this
    },
  });
  // ...
}
```

## ⚠️ Important Notes

These apply to the **calendar** files above, not to the whole directory:

- `api/calendar.ts`, `api/types.ts` and `components/HealthCheck.tsx` are
  **placeholder/boilerplate only** — of those, just the health endpoint works
- Future calendar endpoints are commented out as examples
- DO NOT implement calendar features until the backend is ready

`hooks/useCursors.ts` is not boilerplate: it is a working client for the
endpoint documented below.

---

# Live cursors (`WS /site/ws/cursors`)

Multiplayer cursors: everyone on the same page sees everyone else's pointer.
`src/hooks/useCursors.ts` is a working client — the rest of this section is the
contract it implements, for when you want to write your own.

## Connecting

```
wss://api.vuhnger.dev/site/ws/cursors?room=<room>
```

`room` is the presence scope — peers only see each other inside the same room.
Pass `location.pathname` for per-page presence, or a constant for one shared
room. It defaults to `/`, may be at most 64 characters, and is restricted to
`A-Z a-z 0-9 / _ . -`; anything else is refused at the handshake.

`/v1/site/ws/cursors` is the same endpoint under the versioned prefix.

The `Origin` header is checked against the same allowlist as CORS. That check is
not redundant with CORS: browsers send `Origin` on a WebSocket handshake but
enforce nothing themselves, so without it any site could open this channel.

## Messages

Client → server:

| Message | Meaning |
| --- | --- |
| `{"t":"cursor","x":0.51,"y":0.28}` | Pointer position, as **fractions of the viewport**. Values outside `[0,1]` are clamped, not rejected. |
| `{"t":"ping"}` | Answered with `{"t":"pong"}`. Also what keeps an idle tab from being closed. |

Server → client:

| Message | Meaning |
| --- | --- |
| `{"t":"welcome","id":..,"color":"#e11d48","room":..,"peers":[..],"tick_hz":15,"idle_timeout_seconds":900}` | First message. `peers` is the full room state; everything after it is a delta. |
| `{"t":"join","id":..,"color":..}` | Someone arrived. |
| `{"t":"leave","id":..}` | Someone left. |
| `{"t":"frame","c":{"<id>":[x,y]}}` | Positions that changed since the last tick. |
| `{"t":"pong"}` | Reply to your ping. |
| `{"t":"error","code":".."}` | Sent just before a close, explaining it. |

**Coordinates are viewport fractions, not pixels**, so a phone and a 4K monitor
agree on where the cursor is. Multiply by the container's size to draw.

**`frame` includes your own cursor.** The same bytes go to the whole room rather
than being re-serialised per recipient; drop your own id (from `welcome`).

**`frame` only contains peers that moved.** A still room sends nothing at all.

## Colour

The server assigns each peer a colour, unique within the room while both are in
it, so all clients agree on who is who — two browsers picking their own would
sometimes pick the same one. Ignore it and use your own if you prefer.

## Rate and pacing

The server batches: it collects positions and emits one combined frame at
`tick_hz` (15 by default), so sending faster than that gains nothing — the extra
samples are collapsed into the same frame. Sample `pointermove` into a variable
and send on a timer. Above 60 messages/second the connection is closed.

## Closes, and which ones to retry

| Code | Meaning | Retry? |
| --- | --- | --- |
| `1008` | Policy: bad origin, bad room name, too many tabs from your IP, or a stream of malformed frames. | **No.** Nothing about retrying changes the answer. |
| `1013` | Full: the server, the room, or the room count is at capacity. | Yes, with backoff. |
| `1012` | Server restarting (deploy). Uvicorn sends this itself — it closes connections before the app's own shutdown hook runs, so `1001` shows up only under `--reload` in development. | Yes, with backoff. |
| `1000` | Normal close, including the idle timeout below. | Yes, with backoff. |
| `1006` | Abnormal — the socket died without a close frame. | Yes, with backoff. |

Everything except `1008` is worth retrying, which is what `useCursors.ts` does.
A consequence worth knowing: a backgrounded tab is closed with `1000` after the
idle timeout, reconnects, goes idle again, and repeats — one handshake every 15
minutes per abandoned tab. That is cheap enough to accept, and the per-IP cap
bounds it; reconnecting only on `visibilitychange` would avoid it entirely if it
ever stops being cheap.

Back off exponentially **with jitter**. The interesting failure is a restart,
when every open tab reconnects at once; a fixed delay makes them all arrive
together and turns a 5-second deploy into a thundering herd.

## Idle

A connection that sends nothing for `idle_timeout_seconds` (15 min) is closed.
That is deliberate — a tab nobody is looking at is not presence. Ping every 30 s
while `document.hidden` is false and a backgrounded tab drops out on its own.

## Limits

Defaults, all tunable per environment (`CURSOR_*` in `docker-compose.yml`):
200 connections total, 50 per room, 5 per IP, 100 rooms.
`GET /site/cursors/stats` returns the aggregate load.

The hub is in-memory and **single-worker**: two uvicorn workers would split each
room in half and peers would stop seeing each other. Scaling past one worker
means a Redis pub/sub backend, not a bigger box.

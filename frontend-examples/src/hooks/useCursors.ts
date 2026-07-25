/**
 * Live cursor presence — see everyone else's pointer on the same page.
 *
 * Connects to `WS /site/ws/cursors`, streams this tab's pointer position, and
 * returns the other peers currently in the room.
 *
 * Two things the backend deliberately leaves to you:
 *
 *  - *Rendering.* You get a colour and a position per peer; how a cursor looks,
 *    and whether you interpolate between frames, is yours.
 *  - *Choosing the room.* Peers only see each other inside the same room, so the
 *    room name is what decides "same page" — pass `location.pathname` for
 *    per-page presence, or a constant for one shared room across the whole site.
 *
 * Coordinates are fractions of the viewport, not pixels: a phone and a 4K
 * monitor have to agree on where the cursor is. Multiply back by the container's
 * size when you draw.
 *
 * @example
 *   const { peers, self } = useCursors({ room: location.pathname });
 *   return peers.map(p => (
 *     <div key={p.id} style={{
 *       position: 'fixed', left: `${p.x * 100}%`, top: `${p.y * 100}%`,
 *       background: p.color, transition: 'left 80ms linear, top 80ms linear',
 *     }} />
 *   ));
 */

import { useEffect, useRef, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'https://api.vuhnger.dev';

export interface Peer {
  id: string;
  /** Server-assigned, unique within the room while you are both in it. */
  color: string;
  /** Viewport fractions in [0, 1]. */
  x: number;
  y: number;
}

export interface UseCursorsOptions {
  /** Presence scope. Peers only see each other within the same room. */
  room?: string;
  /**
   * Pointer samples sent per second. There is no point exceeding the server's
   * broadcast rate (`tick_hz`, 15 by default) — anything above it is collapsed
   * into the same frame and only costs the visitor's battery.
   */
  sendHz?: number;
  enabled?: boolean;
}

export interface UseCursorsResult {
  peers: Peer[];
  /** This tab's own id and colour, or null until the socket is open. */
  self: { id: string; color: string } | null;
  connected: boolean;
}

type ServerMessage =
  | { t: 'welcome'; id: string; color: string; room: string; peers: Peer[]; tick_hz: number; idle_timeout_seconds: number }
  | { t: 'join'; id: string; color: string }
  | { t: 'leave'; id: string }
  | { t: 'frame'; c: Record<string, [number, number]> }
  | { t: 'pong' }
  | { t: 'error'; code: string };

/** Close codes the server uses to say "full, but you may come back". */
const RETRYABLE_CLOSE = 1013;

export function useCursors(options: UseCursorsOptions = {}): UseCursorsResult {
  const { room = '/', sendHz = 15, enabled = true } = options;

  const [peers, setPeers] = useState<Peer[]>([]);
  const [self, setSelf] = useState<{ id: string; color: string } | null>(null);
  const [connected, setConnected] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  // Latest pointer position, sampled on a timer rather than sent on every
  // mousemove: a trackpad fires 100+ events a second and the server collapses
  // them anyway, so sending each one is pure waste on both ends.
  const pending = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    if (!enabled) return;

    let closed = false;
    let retry = 0;
    let reconnectTimer: number | undefined;
    let sendTimer: number | undefined;
    let pingTimer: number | undefined;

    const connect = () => {
      if (closed) return;

      const url = new URL('/site/ws/cursors', API_BASE);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      url.searchParams.set('room', room);

      const socket = new WebSocket(url);
      socketRef.current = socket;

      // Every callback below is gated on this. A socket's events keep arriving
      // after it has been superseded — change `room` and the old socket's
      // `onclose` fires *after* the new one has already opened, so an ungated
      // setConnected(false) would report the live connection as dead, and a
      // late `frame` would write the old room's peers over the new room's.
      const current = () => !closed && socketRef.current === socket;

      socket.onopen = () => {
        if (!current()) return;
        retry = 0;
        setConnected(true);
      };

      socket.onmessage = (event) => {
        if (!current()) return;
        const message: ServerMessage = JSON.parse(event.data);
        switch (message.t) {
          case 'welcome':
            setSelf({ id: message.id, color: message.color });
            setPeers(message.peers);
            break;
          case 'join':
            setPeers((prev) => [...prev, { id: message.id, color: message.color, x: 0.5, y: 0.5 }]);
            break;
          case 'leave':
            setPeers((prev) => prev.filter((p) => p.id !== message.id));
            break;
          case 'frame':
            // One frame carries every peer that moved this tick, including you —
            // the server sends identical bytes to the whole room rather than
            // re-serialising it per recipient. Your own id is dropped here.
            setPeers((prev) =>
              prev.map((p) => {
                const moved = message.c[p.id];
                return moved ? { ...p, x: moved[0], y: moved[1] } : p;
              }),
            );
            break;
          case 'error':
            console.warn('[cursors] refused:', message.code);
            break;
        }
      };

      socket.onclose = (event) => {
        if (!current()) return;
        setConnected(false);
        // Presence is not durable across a disconnect: the peers list describes
        // who is in the room *right now*, and leaving it on screen paints
        // cursors for people who may have gone. The next welcome rebuilds it.
        setPeers([]);
        setSelf(null);
        // 1008 is a policy refusal — a bad origin, a bad room, or too many tabs
        // from this address. Retrying cannot change any of those, and hammering
        // a rejection is how a cap turns into a self-inflicted outage.
        if (event.code === 1008) {
          console.warn('[cursors] refused by server, not retrying:', event.reason);
          return;
        }
        // Exponential backoff with jitter, capped at 30s. Jitter matters: the
        // interesting failure is the server restarting, when every open tab is
        // reconnecting at once and a fixed delay makes them all arrive together.
        const delay = Math.min(30_000, 500 * 2 ** retry) * (0.5 + Math.random());
        retry = Math.min(retry + 1, 6);
        if (event.code === RETRYABLE_CLOSE) console.info('[cursors] server full, retrying');
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    const onPointerMove = (event: PointerEvent) => {
      pending.current = {
        x: event.clientX / window.innerWidth,
        y: event.clientY / window.innerHeight,
      };
    };

    sendTimer = window.setInterval(() => {
      const socket = socketRef.current;
      const next = pending.current;
      if (!next || socket?.readyState !== WebSocket.OPEN) return;
      pending.current = null;
      socket.send(JSON.stringify({ t: 'cursor', x: next.x, y: next.y }));
    }, 1000 / sendHz);

    // Keeps an open-but-still tab alive. The server closes connections that go
    // quiet for `idle_timeout_seconds` (15 min), which is deliberate: a tab
    // nobody is looking at should not occupy a slot. document.hidden is the
    // whole mechanism — a backgrounded tab stops pinging and drops out on its own.
    pingTimer = window.setInterval(() => {
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN && !document.hidden) {
        socket.send(JSON.stringify({ t: 'ping' }));
      }
    }, 30_000);

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    connect();

    return () => {
      closed = true;
      window.removeEventListener('pointermove', onPointerMove);
      window.clearTimeout(reconnectTimer);
      window.clearInterval(sendTimer);
      window.clearInterval(pingTimer);
      socketRef.current?.close(1000, 'unmounted');
      socketRef.current = null;
      // Cleared here too, not just in onclose: on unmount or a room change the
      // close is ours, and `closed` already gated onclose out. Without this the
      // old room's cursors survive into the new one.
      pending.current = null;
      setPeers([]);
      setSelf(null);
      setConnected(false);
    };
  }, [room, sendHz, enabled]);

  return { peers, self, connected };
}

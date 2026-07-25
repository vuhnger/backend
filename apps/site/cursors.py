"""Live cursor presence — a WebSocket room where everyone sees everyone's cursor.

The frontend opens one socket per page, streams its pointer position, and gets
back everyone else's. Colour is assigned here rather than in the browser: two
clients picking their own would sometimes pick the same one, and there is no
other place both of them can agree on. The frontend is free to ignore it.

Three things shape this file, and none of them are optional:

*Fan-out is batched.* A naive "broadcast every message" is O(n²): twenty peers
moving the mouse at 60 Hz is 24 000 messages a second. Instead each peer's latest
position is stored, and one loop per room emits a single combined frame at
``CURSOR_TICK_HZ``. Outbound traffic then scales with the number of peers, not
with how fast their mice move, and a client that spams is only spamming itself.

*Every limit lives here.* The shared middleware stack — rate limiting, body caps
— is registered with ``@app.middleware("http")`` and never sees a WebSocket
scope. So the per-IP, per-room and global caps in this module are not defence in
depth; for this endpoint they are the only defence there is.

*State is per process.* The hub is a plain dict. Two uvicorn workers would each
enforce their own caps and peers in the same room would never see one another —
the same single-worker precondition ``apps.shared.rate_limit`` already documents.
Sharding this across workers means a Redis pub/sub backend, not a bigger dict.

Protocol, all JSON text frames.

Client -> server::

    {"t": "cursor", "x": 0.51, "y": 0.28}   # viewport fractions, clamped to [0,1]
    {"t": "ping"}                           # answered with {"t":"pong"}

Server -> client::

    {"t":"welcome","id":..,"color":"#e11d48","room":"/","peers":[..],
     "tick_hz":15.0,"idle_timeout_seconds":900.0}
    {"t":"join","id":..,"color":..}
    {"t":"leave","id":..}
    {"t":"frame","c":{"<id>":[x,y], ...}}   # only peers that moved this tick
    {"t":"pong"}
    {"t":"error","code":"room_full"}        # sent just before a close

Coordinates are fractions of the viewport rather than pixels so a 4K monitor and
a phone agree on where the cursor is; converting back is ``x * width``.
"""

import asyncio
import contextlib
import json
import logging
import math
import re
import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from apps.shared.config import settings
from apps.shared.cors import is_allowed_origin
from apps.shared.net import client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/site")

# Close codes. 1008 is "policy violation" (you are not allowed), 1013 is "try
# again later" (you would be, but we are full) — the distinction is what lets the
# frontend decide between giving up and backing off.
CLOSE_POLICY = 1008
CLOSE_TRY_LATER = 1013

# Room names come from a query param, so they are attacker-controlled and are the
# one string in this module that gets used as a dict key with a cap on cardinality.
# Restricting the charset keeps them printable in logs and rules out the usual
# lookalike tricks (newlines, control characters, unicode homoglyphs in paths).
_ROOM_RE = re.compile(r"^[A-Za-z0-9/_.-]{1,64}$")
DEFAULT_ROOM = "/"

# Largest text frame we will even try to parse. A cursor update is ~40 bytes; the
# `websockets` library's own limit is 1 MiB, which is four orders of magnitude
# more slack than this protocol can justify.
_MAX_FRAME_CHARS = 512

# Consecutive unparseable frames tolerated before the socket is closed. One is a
# glitch or a version skew; a stream of them is a client that will never work.
_MAX_INVALID_FRAMES = 10

# Distinct, roughly equal-luminance hues that stay legible on both a light and a
# dark page. Assignment prefers whichever is unused in the room, so small rooms
# never collide; past len(PALETTE) peers colours repeat, which is fine — at that
# point the cursors are indistinguishable by position anyway.
PALETTE = (
    "#e11d48",  # rose
    "#0ea5e9",  # sky
    "#22c55e",  # green
    "#f59e0b",  # amber
    "#a855f7",  # purple
    "#14b8a6",  # teal
    "#ef4444",  # red
    "#3b82f6",  # blue
    "#84cc16",  # lime
    "#ec4899",  # pink
    "#f97316",  # orange
    "#6366f1",  # indigo
)


class JoinRejected(Exception):
    """A connection that passed the handshake but has no room to be let into."""

    def __init__(self, reason: str, close_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.close_code = close_code


class _TokenBucket:
    """Per-connection inbound allowance, refilled continuously.

    Deliberately not the shared ``limits`` limiter: that one keys on IP across a
    whole app and stores state in a backend, which is the wrong shape for
    something checked on every frame of a socket that already owns its own state.
    """

    def __init__(self, rate: float, burst: float) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = burst
        self._checked = time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self._tokens = min(self._burst, self._tokens + (now - self._checked) * self._rate)
        self._checked = now
        if self._tokens < 1.0:
            return False
        self._tokens -= 1.0
        return True


@dataclass
class Peer:
    """One connected browser tab."""

    id: str
    color: str
    ip: str
    ws: WebSocket
    room: str
    # Bounded on purpose: see CURSOR_SEND_QUEUE_SIZE. A full queue means the
    # client stopped reading, and the only useful answer is to drop it.
    queue: asyncio.Queue[str]
    bucket: _TokenBucket
    x: float = 0.5
    y: float = 0.5
    # Whether this peer has moved since the last tick. Frames carry only movers,
    # so an idle room costs nothing to broadcast.
    moved: bool = False
    invalid_frames: int = 0
    # Set once the peer has been given up on, so the broadcast loop stops
    # queueing for it and only one close is ever scheduled.
    stalled: bool = False


@dataclass
class Room:
    name: str
    peers: dict[str, Peer] = field(default_factory=dict)
    task: asyncio.Task | None = None


class CursorHub:
    """Owns every room, every peer, and every cap.

    All mutating methods are synchronous and never await, so they run to
    completion between event-loop ticks. That is what makes "check the cap, then
    take the slot" safe without a lock — inserting an await between the two would
    let two connections both pass a check for the last remaining slot.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._per_ip: dict[str, int] = {}
        self._total = 0

    # -- stats ------------------------------------------------------------

    @property
    def connections(self) -> int:
        return self._total

    @property
    def room_count(self) -> int:
        return len(self._rooms)

    def peers_in(self, room: str) -> int:
        found = self._rooms.get(room)
        return len(found.peers) if found else 0

    # -- membership -------------------------------------------------------

    def _pick_color(self, room: Room) -> str:
        taken = {p.color for p in room.peers.values()}
        for color in PALETTE:
            if color not in taken:
                return color
        return PALETTE[len(room.peers) % len(PALETTE)]

    def join(self, *, room_name: str, ws: WebSocket, ip: str) -> Peer:
        """Admit a connection, or raise ``JoinRejected`` saying which cap it hit.

        Order matters: the global cap is checked first because it is the one that
        protects the process, then the per-IP cap (one person's tabs must not
        crowd out everyone else), then the room. Creating a room is itself capped
        — otherwise a single client could mint 100 000 rooms from a query string.
        """
        if self._total >= settings.cursor_max_connections:
            raise JoinRejected("server_full", CLOSE_TRY_LATER)
        if self._per_ip.get(ip, 0) >= settings.cursor_max_per_ip:
            raise JoinRejected("too_many_connections", CLOSE_POLICY)

        room = self._rooms.get(room_name)
        if room is None:
            if len(self._rooms) >= settings.cursor_max_rooms:
                raise JoinRejected("too_many_rooms", CLOSE_TRY_LATER)
            room = Room(name=room_name)
            self._rooms[room_name] = room
        elif len(room.peers) >= settings.cursor_max_per_room:
            raise JoinRejected("room_full", CLOSE_TRY_LATER)

        peer = Peer(
            id=uuid.uuid4().hex[:12],
            color=self._pick_color(room),
            ip=ip,
            ws=ws,
            room=room_name,
            queue=asyncio.Queue(maxsize=settings.cursor_send_queue_size),
            bucket=_TokenBucket(
                rate=settings.cursor_max_messages_per_second,
                burst=settings.cursor_max_messages_per_second * 2,
            ),
        )
        room.peers[peer.id] = peer
        self._per_ip[ip] = self._per_ip.get(ip, 0) + 1
        self._total += 1

        # Started only once the room has someone in it, and stopped again when it
        # empties — an idle loop per abandoned room is exactly the kind of leak
        # that only shows up after a month of uptime.
        if room.task is None:
            room.task = asyncio.create_task(self._broadcast_loop(room))
        return peer

    def leave(self, peer: Peer) -> None:
        """Remove a peer and tear the room down if it was the last one.

        Written to be safe to call twice: the disconnect path and the error path
        both end here, and a double-decrement of ``_total`` would slowly leak
        capacity until the endpoint refused everyone.
        """
        room = self._rooms.get(peer.room)
        if room is None or room.peers.pop(peer.id, None) is None:
            return

        self._total -= 1
        remaining = self._per_ip.get(peer.ip, 0) - 1
        if remaining > 0:
            self._per_ip[peer.ip] = remaining
        else:
            self._per_ip.pop(peer.ip, None)

        if not room.peers:
            if room.task is not None:
                room.task.cancel()
            del self._rooms[peer.room]

    def snapshot(self, room_name: str, *, exclude: str) -> list[dict]:
        """Everyone currently in the room except ``exclude``, with their positions."""
        room = self._rooms.get(room_name)
        if room is None:
            return []
        return [
            {"id": p.id, "color": p.color, "x": round(p.x, 4), "y": round(p.y, 4)}
            for p in room.peers.values()
            if p.id != exclude
        ]

    def send_to(self, peer: Peer, payload: str) -> None:
        """Queue one frame for a single peer (used for welcome and pong)."""
        self._enqueue(peer, payload)

    # -- delivery ---------------------------------------------------------

    def _enqueue(self, peer: Peer, payload: str) -> None:
        """Hand a frame to one peer, or mark it unreachable.

        Never awaits. ``await ws.send_text`` on a stalled client blocks for as
        long as the client feels like, and doing that from the room's broadcast
        loop would let one bad socket freeze the room for everyone in it.
        """
        if peer.stalled:
            return
        try:
            peer.queue.put_nowait(payload)
        except asyncio.QueueFull:
            # Closing is what ends the connection, not cancelling the writer: the
            # reader is parked in receive_text() and only a closed socket wakes it.
            # Left alone it would hold its slot until TCP gives up, which on a
            # half-open connection is minutes.
            logger.info("cursor peer %s fell behind, dropping", peer.id)
            peer.stalled = True
            _cancel_writer(peer)
            _detach(asyncio.create_task(_close_quietly(peer.ws, CLOSE_TRY_LATER)))

    def broadcast(self, room_name: str, payload: str, *, skip: str | None = None) -> None:
        room = self._rooms.get(room_name)
        if room is None:
            return
        # list() because _enqueue can drop a peer, and mutating during iteration
        # would raise and abort delivery to everyone after it.
        for peer in list(room.peers.values()):
            if peer.id != skip:
                self._enqueue(peer, payload)

    async def _broadcast_loop(self, room: Room) -> None:
        """Emit one combined frame per tick, containing only peers that moved.

        Everyone gets the same bytes, including their own cursor. Filtering each
        peer out of its own frame would mean serialising the payload once per
        peer instead of once per room; the client already knows its own id from
        the welcome message and drops it in one line.
        """
        interval = 1.0 / settings.cursor_tick_hz
        try:
            while True:
                await asyncio.sleep(interval)
                movers = {}
                for peer in room.peers.values():
                    if peer.moved:
                        # 4 decimals is ~0.1 px on a 1000 px axis: below what a
                        # screen can show, and it keeps the frame small.
                        movers[peer.id] = [round(peer.x, 4), round(peer.y, 4)]
                        peer.moved = False
                if movers:
                    self.broadcast(room.name, json.dumps({"t": "frame", "c": movers}))
        except asyncio.CancelledError:
            raise
        except Exception:
            # A crashed loop leaves the room silently frozen — connected, sending,
            # and nobody seeing anything. Log it rather than let the task die mute.
            logger.exception("cursor broadcast loop for room %r stopped", room.name)
            raise

    async def shutdown(self) -> None:
        """Stop every room loop and close whatever sockets are still open.

        By the time uvicorn runs this the sockets are usually already closed —
        it shuts connections down before firing lifespan shutdown — so the close
        below is for the cases where that is not true: the ``--reload`` path in
        development, and the tests. The part that always matters is cancelling
        the room tasks, which uvicorn knows nothing about.
        """
        for room in list(self._rooms.values()):
            if room.task is not None:
                room.task.cancel()
            for peer in list(room.peers.values()):
                _cancel_writer(peer)
                with contextlib.suppress(Exception):
                    if peer.ws.client_state is WebSocketState.CONNECTED:
                        await peer.ws.close(code=1001)  # going away
        self._rooms.clear()
        self._per_ip.clear()
        self._total = 0


hub = CursorHub()

# Writer tasks are tracked beside the peer rather than on it so that Peer stays a
# plain data record with no asyncio machinery in its repr (peers get logged).
_writers: dict[str, asyncio.Task] = {}

# asyncio keeps only a weak reference to a running task, so a fire-and-forget one
# can be garbage-collected mid-await. Holding it here until it finishes is the
# documented way to stop that.
_background: set[asyncio.Task] = set()


def _detach(task: asyncio.Task) -> None:
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _close_quietly(ws: WebSocket, code: int) -> None:
    with contextlib.suppress(Exception):
        if ws.client_state is WebSocketState.CONNECTED:
            await ws.close(code=code)


def _cancel_writer(peer: Peer) -> None:
    task = _writers.pop(peer.id, None)
    if task is not None:
        task.cancel()


async def _writer(peer: Peer) -> None:
    """Drain one peer's queue onto its socket.

    One task per connection, so a slow or half-open socket blocks only itself.
    """
    try:
        while True:
            payload = await peer.queue.get()
            await peer.ws.send_text(payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        # Sending to a socket the client already dropped is routine, not an
        # error worth a stack trace; the reader will notice and clean up.
        logger.debug("cursor writer for %s ended", peer.id)


def _valid_room(raw: str | None) -> str | None:
    """Normalise and validate the requested room, or None if it is unusable."""
    name = (raw or DEFAULT_ROOM).strip()
    if not name:
        name = DEFAULT_ROOM
    return name if _ROOM_RE.match(name) else None


def _coord(value: object) -> float | None:
    """A pointer coordinate as a fraction of the viewport, or None if unusable.

    Clamped rather than rejected: a pointer legitimately leaves the viewport
    during a drag, and dropping the connection over an x of 1.0002 would be a
    bug that only shows up on someone else's trackpad. NaN and infinity *are*
    rejected — they survive json.loads, pass a naive range check (every
    comparison against NaN is False), and would poison the frame for every peer.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return min(1.0, max(0.0, number))


@router.get("/cursors/stats")
def cursor_stats():
    """Aggregate load, for a healthcheck or a dashboard.

    Aggregate only: a per-room breakdown would turn an unauthenticated endpoint
    into a live feed of which pages are being read right now, which is precisely
    the visitor data the rest of this service is careful not to publish.
    """
    return {
        "connections": hub.connections,
        "rooms": hub.room_count,
        "max_connections": settings.cursor_max_connections,
    }


@router.websocket("/ws/cursors")
async def cursors_ws(websocket: WebSocket):
    """Cursor presence for one room. See module docstring for the protocol."""
    origin = websocket.headers.get("origin")
    if not is_allowed_origin(origin):
        # Closing before accept() answers the handshake with an HTTP 403, so the
        # rejection is visible in the browser's network tab instead of appearing
        # as a connection that opens and instantly dies.
        logger.warning("cursor ws rejected: origin=%r", origin)
        await websocket.close(code=CLOSE_POLICY)
        return

    room_name = _valid_room(websocket.query_params.get("room"))
    if room_name is None:
        await websocket.close(code=CLOSE_POLICY)
        return

    await websocket.accept()
    ip = client_ip(websocket)

    try:
        peer = hub.join(room_name=room_name, ws=websocket, ip=ip)
    except JoinRejected as rejected:
        # Accepted first, so the reason can be delivered. A bare close code tells
        # the frontend nothing about whether retrying is worth it.
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps({"t": "error", "code": rejected.reason}))
            await websocket.close(code=rejected.close_code)
        return

    _writers[peer.id] = asyncio.create_task(_writer(peer))

    # Full room state, once, at join. Every later message is a delta, which is
    # only coherent because the client starts from this snapshot.
    hub.send_to(
        peer,
        json.dumps(
            {
                "t": "welcome",
                "id": peer.id,
                "color": peer.color,
                "room": room_name,
                "peers": hub.snapshot(room_name, exclude=peer.id),
                "tick_hz": settings.cursor_tick_hz,
                "idle_timeout_seconds": settings.cursor_idle_timeout_seconds,
            }
        ),
    )
    hub.broadcast(
        room_name,
        json.dumps({"t": "join", "id": peer.id, "color": peer.color}),
        skip=peer.id,
    )

    try:
        await _read_loop(peer, websocket)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("cursor ws for %s failed", peer.id)
    finally:
        _cancel_writer(peer)
        # leave() first, so the departing peer isn't among the recipients of its
        # own leave message — and so the slot is freed even if broadcasting fails.
        hub.leave(peer)
        hub.broadcast(room_name, json.dumps({"t": "leave", "id": peer.id}))
        await _close_quietly(websocket, 1000)


async def _read_loop(peer: Peer, websocket: WebSocket) -> None:
    """Consume client frames until it disconnects, idles out, or misbehaves."""
    idle = settings.cursor_idle_timeout_seconds
    while True:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=idle)
        except TimeoutError:
            # Not a failure: a backgrounded tab stops pinging, and a tab nobody
            # is looking at is not a cursor anyone needs to see. Freeing the slot
            # is the point.
            logger.debug("cursor peer %s idled out", peer.id)
            return

        if not peer.bucket.take():
            logger.info("cursor peer %s exceeded the inbound rate, closing", peer.id)
            await websocket.close(code=CLOSE_POLICY)
            return

        # Oversized frames are counted as invalid rather than parsed: json.loads
        # on an attacker-sized string is the work we are trying to avoid doing.
        peer.invalid_frames = (
            peer.invalid_frames + 1 if len(raw) > _MAX_FRAME_CHARS else _handle_frame(peer, raw)
        )

        if peer.stalled:
            # Already given up on by the broadcast loop (see _enqueue). Return so
            # the caller's finally block runs and the slot is actually released.
            return

        if peer.invalid_frames >= _MAX_INVALID_FRAMES:
            logger.info("cursor peer %s sent only garbage, closing", peer.id)
            await websocket.close(code=CLOSE_POLICY)
            return


def _handle_frame(peer: Peer, raw: str) -> int:
    """Apply one client frame. Returns the peer's new invalid-frame count.

    Movement is recorded, never forwarded: the room's tick loop is what actually
    sends it. That is the whole reason a client cannot flood the room by
    flooding us.
    """
    try:
        message = json.loads(raw)
    except (ValueError, TypeError):
        return peer.invalid_frames + 1
    if not isinstance(message, dict):
        return peer.invalid_frames + 1

    kind = message.get("t")
    if kind == "cursor":
        x = _coord(message.get("x"))
        y = _coord(message.get("y"))
        if x is None or y is None:
            return peer.invalid_frames + 1
        peer.x, peer.y, peer.moved = x, y, True
        return 0
    if kind == "ping":
        # Round-trip for the client's own liveness check, and what keeps an
        # active tab from tripping the idle timeout. Routed through the hub so a
        # peer whose queue is already full gets dropped here too, rather than
        # having its pong silently swallowed while it believes it is connected.
        hub.send_to(peer, json.dumps({"t": "pong"}))
        return 0
    return peer.invalid_frames + 1

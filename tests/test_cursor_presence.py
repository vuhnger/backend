"""Live cursor presence: the hub's caps and bookkeeping, and the wire protocol.

Split in two on purpose. Starlette's TestClient runs *every* WebSocket session in
its own event loop, and ``asyncio.Queue.put_nowait`` wakes a waiting ``get()`` by
resolving that loop's future directly — which is not safe to do from another
thread. A two-client TestClient test therefore races, and passes or hangs by
luck. Production has one uvicorn process and one loop, so the race cannot happen
there; rather than harden the code against a situation it will never be in, the
multi-peer behaviour is exercised against the hub inside a single loop, and
TestClient is used only where one connection is enough.
"""

import asyncio
import json

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect, WebSocketState

import apps.shared.cors as cors
import apps.site.cursors as cursors
import apps.site.main as site
from apps.site.cursors import PALETTE, CursorHub, JoinRejected, _coord, _TokenBucket, _valid_room


class FakeWS:
    """Just enough WebSocket for the hub: it never sends, only records."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed_with: int | None = None
        self.client_state = WebSocketState.CONNECTED

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code
        self.client_state = WebSocketState.DISCONNECTED


@pytest.fixture
async def hub():
    """A fresh hub inside a running loop.

    Async because ``join()`` starts the room's broadcast task, so there has to be
    a loop to start it on — and because the teardown has to cancel those tasks,
    or every hub test leaves a live loop behind for the next one to trip over.
    """
    fresh = CursorHub()
    yield fresh
    await fresh.shutdown()


def drain(peer) -> list[dict]:
    """Everything queued for a peer, decoded. Nothing is sent without a writer task."""
    out = []
    while not peer.queue.empty():
        out.append(json.loads(peer.queue.get_nowait()))
    return out


# --- caps ------------------------------------------------------------------

async def test_global_cap_rejects_with_try_later(hub, monkeypatch):
    monkeypatch.setattr(cursors.settings, "cursor_max_connections", 2)
    for i in range(2):
        hub.join(room_name="/a", ws=FakeWS(), ip=f"10.0.0.{i}")
    with pytest.raises(JoinRejected) as excinfo:
        hub.join(room_name="/a", ws=FakeWS(), ip="10.0.0.9")
    # try-later, not policy: the client should back off and retry, not give up.
    assert excinfo.value.reason == "server_full"
    assert excinfo.value.close_code == cursors.CLOSE_TRY_LATER


async def test_per_ip_cap_does_not_block_other_visitors(hub, monkeypatch):
    monkeypatch.setattr(cursors.settings, "cursor_max_per_ip", 2)
    for _ in range(2):
        hub.join(room_name="/a", ws=FakeWS(), ip="1.2.3.4")
    with pytest.raises(JoinRejected) as excinfo:
        hub.join(room_name="/a", ws=FakeWS(), ip="1.2.3.4")
    assert excinfo.value.reason == "too_many_connections"
    # The whole point of a *per-IP* cap: one person's tabs must not lock out anyone else.
    assert hub.join(room_name="/a", ws=FakeWS(), ip="5.6.7.8") is not None


async def test_room_cap_is_per_room_not_global(hub, monkeypatch):
    monkeypatch.setattr(cursors.settings, "cursor_max_per_room", 1)
    hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    with pytest.raises(JoinRejected) as excinfo:
        hub.join(room_name="/a", ws=FakeWS(), ip="2.2.2.2")
    assert excinfo.value.reason == "room_full"
    assert hub.join(room_name="/b", ws=FakeWS(), ip="3.3.3.3") is not None


async def test_room_creation_is_capped(hub, monkeypatch):
    """Room names come from a query param, so an uncapped dict is a memory leak
    any single client can trigger."""
    monkeypatch.setattr(cursors.settings, "cursor_max_rooms", 2)
    hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    hub.join(room_name="/b", ws=FakeWS(), ip="1.1.1.2")
    with pytest.raises(JoinRejected) as excinfo:
        hub.join(room_name="/c", ws=FakeWS(), ip="1.1.1.3")
    assert excinfo.value.reason == "too_many_rooms"


# --- bookkeeping -----------------------------------------------------------

async def test_leave_frees_the_slot_and_the_room(hub):
    peer = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    assert (hub.connections, hub.room_count) == (1, 1)
    hub.leave(peer)
    assert (hub.connections, hub.room_count) == (0, 0)


async def test_leave_is_idempotent(hub):
    """The disconnect path and the error path both end in leave(). A second call
    that decremented again would leak capacity until the endpoint refused everyone."""
    peer = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    hub.leave(peer)
    hub.leave(peer)
    assert hub.connections == 0
    assert hub._per_ip == {}


async def test_colors_are_distinct_within_a_room(hub):
    peers = [hub.join(room_name="/a", ws=FakeWS(), ip=f"1.1.1.{i}") for i in range(5)]
    assert len({p.color for p in peers}) == 5
    assert all(p.color in PALETTE for p in peers)


async def test_color_is_reused_once_its_owner_leaves(hub):
    first = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    hub.leave(first)
    second = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.2")
    assert second.color == first.color


async def test_snapshot_excludes_the_joiner(hub):
    a = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    b = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.2")
    ids = {entry["id"] for entry in hub.snapshot("/a", exclude=b.id)}
    assert ids == {a.id}


# --- delivery --------------------------------------------------------------

async def test_broadcast_reaches_everyone_but_the_sender(hub):
    a = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    b = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.2")
    hub.broadcast("/a", json.dumps({"t": "join", "id": a.id}), skip=a.id)
    assert drain(a) == []
    assert drain(b) == [{"t": "join", "id": a.id}]


async def test_a_slow_peer_is_dropped_rather_than_buffered_forever(hub, monkeypatch):
    monkeypatch.setattr(cursors.settings, "cursor_send_queue_size", 2)
    slow = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    fast = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.2")
    for _ in range(5):
        hub.broadcast("/a", json.dumps({"t": "frame", "c": {}}))
        drain(fast)  # the healthy peer keeps up

    assert slow.stalled is True
    # And nothing further is queued for it — a stalled peer must stop costing memory.
    depth = slow.queue.qsize()
    hub.broadcast("/a", json.dumps({"t": "frame", "c": {}}))
    assert slow.queue.qsize() == depth


async def test_broadcast_loop_batches_only_movers(hub, monkeypatch):
    """The whole reason fan-out is not O(n²): many moves collapse into one frame,
    and a peer that did not move is not in it at all."""
    monkeypatch.setattr(cursors.settings, "cursor_tick_hz", 50.0)
    mover = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    still = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.2")
    drain(mover), drain(still)

    for value in (0.1, 0.2, 0.3):  # three moves inside one tick
        mover.x, mover.y, mover.moved = value, value, True
    await asyncio.sleep(0.1)

    frames = [m for m in drain(still) if m["t"] == "frame"]
    assert len(frames) == 1, f"expected one batched frame, got {frames}"
    assert frames[0]["c"] == {mover.id: [0.3, 0.3]}  # last position wins
    assert mover.id in frames[0]["c"] and still.id not in frames[0]["c"]


async def test_idle_room_broadcasts_nothing(hub, monkeypatch):
    monkeypatch.setattr(cursors.settings, "cursor_tick_hz", 50.0)
    peer = hub.join(room_name="/a", ws=FakeWS(), ip="1.1.1.1")
    drain(peer)
    await asyncio.sleep(0.1)
    assert drain(peer) == []


async def test_shutdown_closes_sockets_with_going_away(hub):
    sockets = [FakeWS() for _ in range(3)]
    for i, ws in enumerate(sockets):
        hub.join(room_name="/a", ws=ws, ip=f"1.1.1.{i}")
    await hub.shutdown()
    assert hub.connections == 0
    # 1001 "going away", not a silent drop: a dropped socket reads as a network
    # fault and every tab answers it with an immediate reconnect.
    assert [ws.closed_with for ws in sockets] == [1001, 1001, 1001]


# --- input validation ------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.5, 0.5),
        (0, 0.0),
        (1, 1.0),
        (-0.2, 0.0),   # clamped: a pointer legitimately leaves the viewport
        (1.4, 1.0),
        (float("nan"), None),   # survives json.loads and defeats naive range checks
        (float("inf"), None),
        ("0.5", None),
        (None, None),
        (True, None),  # bool is an int subclass; a cursor at x=True is nonsense
    ],
)
def test_coord_clamps_the_plausible_and_rejects_the_impossible(raw, expected):
    assert _coord(raw) == expected


@pytest.mark.parametrize("name", ["/", "/blog", "a-b_c.d", "/x/y/z"])
def test_valid_room_names(name):
    assert _valid_room(name) == name


@pytest.mark.parametrize("name", ["with space", "x" * 65, "ny\nlinje", "emoji🎉", "sem;colon"])
def test_invalid_room_names_are_rejected(name):
    assert _valid_room(name) is None


def test_missing_room_falls_back_to_default():
    assert _valid_room(None) == cursors.DEFAULT_ROOM
    assert _valid_room("  ") == cursors.DEFAULT_ROOM


def test_token_bucket_allows_a_burst_then_refills():
    bucket = _TokenBucket(rate=10.0, burst=3.0)
    assert [bucket.take() for _ in range(4)] == [True, True, True, False]


# --- wire protocol (single connection) -------------------------------------

@pytest.fixture
def client():
    with TestClient(site.app) as test_client:
        yield test_client
    # The app singleton is shared across tests; a leaked peer would skew the caps
    # every later test asserts on.
    cursors.hub._rooms.clear()
    cursors.hub._per_ip.clear()
    cursors.hub._total = 0


def test_welcome_carries_identity_and_the_client_side_contract(client):
    with client.websocket_connect("/site/ws/cursors?room=/blog") as ws:
        welcome = ws.receive_json()
    assert welcome["t"] == "welcome"
    assert welcome["room"] == "/blog"
    assert welcome["color"] in PALETTE
    assert welcome["peers"] == []
    # Both are the frontend's contract: how often frames arrive, and how long it
    # may stay silent before being closed. Hardcoding either in the client is how
    # a server-side tuning change silently breaks it.
    assert welcome["tick_hz"] > 0
    assert welcome["idle_timeout_seconds"] > 0


def test_cursor_update_comes_back_as_a_frame(client):
    with client.websocket_connect("/site/ws/cursors") as ws:
        ws.receive_json()
        ws.send_json({"t": "cursor", "x": 0.25, "y": 0.75})
        frame = ws.receive_json()
    assert frame["t"] == "frame"
    assert list(frame["c"].values()) == [[0.25, 0.75]]


def test_out_of_range_coordinates_are_clamped_not_refused(client):
    with client.websocket_connect("/site/ws/cursors") as ws:
        ws.receive_json()
        ws.send_json({"t": "cursor", "x": -3, "y": 9})
        frame = ws.receive_json()
    assert list(frame["c"].values()) == [[0.0, 1.0]]


def test_ping_is_answered(client):
    with client.websocket_connect("/site/ws/cursors") as ws:
        ws.receive_json()
        ws.send_json({"t": "ping"})
        assert ws.receive_json() == {"t": "pong"}


def test_a_stream_of_garbage_closes_the_connection(client):
    with client.websocket_connect("/site/ws/cursors") as ws:
        ws.receive_json()
        for _ in range(cursors._MAX_INVALID_FRAMES):
            ws.send_text("not json at all")
        with pytest.raises(WebSocketDisconnect):
            # Either a close frame or a disconnect — both mean the socket is gone.
            for _ in range(3):
                ws.receive_json()


def test_a_single_bad_frame_is_survivable(client):
    """Version skew and stray keepalives happen; one bad frame must not be fatal."""
    with client.websocket_connect("/site/ws/cursors") as ws:
        ws.receive_json()
        ws.send_text("{oops")
        ws.send_json({"t": "cursor", "x": 0.4, "y": 0.4})
        frame = ws.receive_json()
    assert list(frame["c"].values()) == [[0.4, 0.4]]


def test_an_oversized_frame_is_not_parsed(client):
    with client.websocket_connect("/site/ws/cursors") as ws:
        ws.receive_json()
        ws.send_json({"t": "cursor", "x": 0.1, "y": 0.1, "pad": "A" * cursors._MAX_FRAME_CHARS})
        ws.send_json({"t": "cursor", "x": 0.6, "y": 0.6})
        frame = ws.receive_json()
    # The padded frame carried a valid position; it must still have been discarded.
    assert list(frame["c"].values()) == [[0.6, 0.6]]


def test_an_invalid_room_name_is_refused_at_the_handshake(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/site/ws/cursors?room=not a room") as ws:
            ws.receive_json()


def test_the_versioned_alias_serves_the_same_endpoint(client):
    with client.websocket_connect("/v1/site/ws/cursors") as ws:
        assert ws.receive_json()["t"] == "welcome"


def test_stats_are_aggregate_only(client):
    body = client.get("/site/cursors/stats").json()
    # No room names and no IPs: this endpoint is unauthenticated, and a per-room
    # breakdown would be a live feed of which pages are being read right now.
    assert set(body) == {"connections", "rooms", "max_connections"}


# --- origin ----------------------------------------------------------------

def test_a_foreign_origin_is_refused(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/site/ws/cursors", headers={"origin": "https://evil.example.com"}
        ) as ws:
            ws.receive_json()


def test_an_allowed_origin_gets_through(client):
    with client.websocket_connect(
        "/site/ws/cursors", headers={"origin": "https://vuhnger.dev"}
    ) as ws:
        assert ws.receive_json()["t"] == "welcome"


def test_a_trailing_slash_on_the_origin_still_matches():
    # Some clients send "https://vuhnger.dev/"; refusing it would be a real
    # outage for a difference the browser considers cosmetic.
    assert cors.is_allowed_origin("https://vuhnger.dev/")


def test_a_missing_origin_is_allowed_outside_production_only(monkeypatch):
    """WebSocket has no preflight, so Origin is the only signal we get. A request
    without one is not a browser; in production there is no legitimate such client."""
    monkeypatch.setattr(cors.settings, "environment", "development")
    assert cors.is_allowed_origin(None) is True
    monkeypatch.setattr(cors.settings, "environment", "production")
    assert cors.is_allowed_origin(None) is False

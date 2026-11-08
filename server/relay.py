#!/usr/bin/env python3
"""Zombie Outbreak V7 - worldwide online relay (V7_ONLINE_1).

Players anywhere in the world (mobile data, home Wi-Fi, behind any router) connect OUT to this
server over a WebSocket, so nobody needs a public IP or port forwarding. The host player's game
stays in charge of the match exactly like a LAN game; this server only forwards packets
between the host (peer 1) and the other players, and keeps a list of open rooms.

Pure Python standard library - no packages to install. Runs on any host that gives you one web
port (Render, Koyeb, Railway, Fly.io, a VPS ...). It listens on $PORT (default 8080).

  GET  /            health check text          GET /rooms   open rooms as JSON
  GET  /health      "ok"                       WS  /ws      game connection (see protocol below)

Protocol (one WebSocket per player):
  text  -> {"op":"host", "name","map","mode","variant","max","edition","build"}  <- {"op":"hosted","code","id":1}
  text  -> {"op":"join", "code","edition","build"}                                 <- {"op":"joined","id","code"}
  text  -> {"op":"info", ...room fields} (host only)       text <- {"op":"peer_in"/"peer_out","id"} (host only)
  text  -> {"op":"kick","id"} (host only)                  text <- {"op":"error","msg"} / {"op":"closed"}
  binary-> [0x01][target int32 LE][payload]  (host: target 0 = all, n = player n, -n = all but n;
                                              players: always delivered to the host)
  binary<- [0x01][sender int32 LE][payload]
"""
import asyncio
import base64
import hashlib
import json
import os
import random
import struct
import time

PORT = int(os.environ.get("PORT", "8080"))
MAX_ROOMS = int(os.environ.get("MAX_ROOMS", "300"))
MAX_PLAYERS = 10                 # 5v5
MAX_FRAME = 512 * 1024           # biggest single message accepted
MAX_BACKLOG = 4 * 1024 * 1024    # a player whose connection can't keep up is dropped
PING_EVERY = 20.0
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

rooms = {}                       # code -> Room
stats = {"started": time.time(), "connections": 0, "rooms_made": 0}


def clean(value, n=40):
    return "".join(ch for ch in str(value) if ch.isprintable())[:n]


class Conn:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.room = None
        self.id = 0
        self.alive = True

    async def send_frame(self, opcode, payload):
        if not self.alive:
            return
        n = len(payload)
        if n < 126:
            head = struct.pack("!BB", 0x80 | opcode, n)
        elif n < 65536:
            head = struct.pack("!BBH", 0x80 | opcode, 126, n)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 127, n)
        try:
            self.writer.write(head + payload)
            transport = self.writer.transport
            if transport is not None and transport.get_write_buffer_size() > MAX_BACKLOG:
                self.close()
                return
            await self.writer.drain()
        except (ConnectionError, RuntimeError, OSError):
            self.close()

    def send_json(self, obj):
        asyncio.ensure_future(self.send_frame(0x1, json.dumps(obj, separators=(",", ":")).encode()))

    def send_data(self, sender, payload):
        asyncio.ensure_future(self.send_frame(0x2, b"\x01" + struct.pack("<i", sender) + payload))

    def close(self):
        if self.alive:
            self.alive = False
            try:
                self.writer.close()
            except Exception:
                pass


class Room:
    def __init__(self, code, host, info):
        self.code = code
        self.host = host
        self.players = {}            # id -> Conn (not the host)
        self.created = time.time()
        self.info = {}
        self.update(info)

    def update(self, info):
        for key, n in (("name", 32), ("map", 32), ("mode", 12), ("variant", 12), ("state", 12), ("edition", 12)):
            if key in info:
                self.info[key] = clean(info[key], n)
        for key in ("max", "build", "players", "ranked"):
            if key in info:
                try:
                    self.info[key] = int(info[key])
                except (TypeError, ValueError):
                    pass
        if "names" in info and isinstance(info["names"], list):
            self.info["names"] = [clean(x, 18) for x in info["names"][:MAX_PLAYERS]]
        self.info["max"] = max(2, min(MAX_PLAYERS, int(self.info.get("max", MAX_PLAYERS))))

    def public(self):
        d = dict(self.info)
        d["code"] = self.code
        d["players"] = 1 + len(self.players)
        d.setdefault("state", "waiting")
        d["age"] = int(time.time() - self.created)
        return d

    def new_id(self):
        while True:
            i = random.randint(2, 2_000_000_000)
            if i not in self.players:
                return i


def new_code():
    for _ in range(1000):
        code = "".join(random.choice(CODE_CHARS) for _ in range(5))
        if code not in rooms:
            return code
    raise RuntimeError("no free room code")


# ------------------------------------------------------------------ game messages
def on_text(c, text):
    try:
        msg = json.loads(text)
    except ValueError:
        return
    if not isinstance(msg, dict):
        return
    op = msg.get("op")
    if op == "host" and c.room is None:
        if len(rooms) >= MAX_ROOMS:
            c.send_json({"op": "error", "msg": "Server is full - try again in a minute"})
            return
        code = new_code()
        room = Room(code, c, msg)
        rooms[code] = room
        c.room, c.id = room, 1
        stats["rooms_made"] += 1
        c.send_json({"op": "hosted", "code": code, "id": 1})
    elif op == "join" and c.room is None:
        room = rooms.get(clean(msg.get("code", ""), 8).upper())
        if room is None:
            c.send_json({"op": "error", "msg": "Room not found - check the code"})
            return
        if room.info.get("build") is not None and msg.get("build") is not None and int(msg.get("build", 0)) != room.info.get("build"):
            c.send_json({"op": "error", "msg": "That room runs another game version - update the game"})
            return
        if 1 + len(room.players) >= room.info.get("max", MAX_PLAYERS):
            c.send_json({"op": "error", "msg": "Room is full"})
            return
        c.room, c.id = room, room.new_id()
        room.players[c.id] = c
        c.send_json({"op": "joined", "id": c.id, "code": room.code})
        room.host.send_json({"op": "peer_in", "id": c.id})
    elif op == "info" and c.room is not None and c.id == 1:
        c.room.update(msg)
    elif op == "kick" and c.room is not None and c.id == 1:
        target = c.room.players.get(int(msg.get("id", 0) or 0))
        if target is not None:
            target.send_json({"op": "closed", "msg": "Removed by the host"})
            asyncio.get_event_loop().call_later(0.3, target.close)


def on_binary(c, data):
    room = c.room
    if room is None or len(data) < 5 or data[0] != 0x01:
        return
    target = struct.unpack_from("<i", data, 1)[0]
    payload = bytes(data[5:])
    if c.id != 1:
        room.host.send_data(c.id, payload)
        return
    if target == 0:
        for p in list(room.players.values()):
            p.send_data(1, payload)
    elif target > 0:
        p = room.players.get(target)
        if p is not None:
            p.send_data(1, payload)
    else:
        for pid, p in list(room.players.items()):
            if pid != -target:
                p.send_data(1, payload)


def on_leave(c):
    room = c.room
    c.room = None
    if room is None:
        return
    if c.id == 1:
        rooms.pop(room.code, None)
        for p in list(room.players.values()):
            p.send_json({"op": "closed", "msg": "The host left"})
            asyncio.get_event_loop().call_later(0.3, p.close)
        room.players.clear()
    else:
        room.players.pop(c.id, None)
        room.host.send_json({"op": "peer_out", "id": c.id})


# ------------------------------------------------------------------ WebSocket plumbing
async def read_frames(c):
    """Yields (opcode, payload) for complete messages; answers pings, handles fragments."""
    parts, first_op = [], 0
    while True:
        b1, b2 = await c.reader.readexactly(2)
        fin, op = b1 & 0x80, b1 & 0x0F
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack("!H", await c.reader.readexactly(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", await c.reader.readexactly(8))[0]
        if n > MAX_FRAME:
            raise ConnectionError("frame too big")
        mask = await c.reader.readexactly(4) if b2 & 0x80 else None
        data = await c.reader.readexactly(n) if n else b""
        if mask and n:
            data = _unmask(data, mask)
        if op == 0x8:                                   # close
            await c.send_frame(0x8, data[:2])
            return
        if op == 0x9:                                   # ping
            await c.send_frame(0xA, data)
            continue
        if op == 0xA:                                   # pong
            continue
        if op in (0x1, 0x2):
            parts, first_op = [data], op
        elif op == 0x0:
            parts.append(data)
            if sum(len(p) for p in parts) > MAX_FRAME:
                raise ConnectionError("message too big")
        if fin and parts:
            yield first_op, b"".join(parts)
            parts = []


def _unmask(data, mask):
    n = len(data)
    m = int.from_bytes((mask * ((n + 3) // 4))[:n], "little")
    return (int.from_bytes(data, "little") ^ m).to_bytes(n, "little")


async def pinger(c):
    while c.alive:
        await asyncio.sleep(PING_EVERY)
        await c.send_frame(0x9, b"zo")


async def http_reply(writer, status, body, ctype="text/plain; charset=utf-8"):
    head = (f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
            "Access-Control-Allow-Origin: *\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n")
    writer.write(head.encode() + body)
    try:
        await writer.drain()
    finally:
        writer.close()


async def handle(reader, writer):
    try:
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 15)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        writer.close()
        return
    lines = raw.decode("latin-1").split("\r\n")
    try:
        method, path, _ = lines[0].split(" ", 2)
    except ValueError:
        writer.close()
        return
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    path = path.split("?", 1)[0]
    if headers.get("upgrade", "").lower() != "websocket":
        if path == "/rooms":
            body = json.dumps([r.public() for r in rooms.values()], separators=(",", ":")).encode()
            await http_reply(writer, "200 OK", body, "application/json")
        elif path in ("/", "/health"):
            text = "ok" if path == "/health" else (
                "Zombie Outbreak V7 online relay - %d rooms, %d players online\n"
                % (len(rooms), sum(1 + len(r.players) for r in rooms.values())))
            await http_reply(writer, "200 OK", text.encode())
        else:
            await http_reply(writer, "404 Not Found", b"not found")
        return
    key = headers.get("sec-websocket-key", "")
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
    await writer.drain()
    c = Conn(reader, writer)
    stats["connections"] += 1
    ping_task = asyncio.ensure_future(pinger(c))
    try:
        async for op, data in read_frames(c):
            if op == 0x1:
                on_text(c, data.decode("utf-8", "replace"))
            else:
                on_binary(c, data)
    except (asyncio.IncompleteReadError, ConnectionError, OSError, ValueError):
        pass
    finally:
        ping_task.cancel()
        on_leave(c)
        c.close()


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", PORT, limit=64 * 1024)
    print(f"Zombie Outbreak relay listening on port {PORT}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

"""One bounded upstream reader; immutable local snapshots and sampled history."""
import collections
import gzip
import http.client
import json
import math
import threading
import time
import urllib.parse
import uuid
import zlib


def encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Settings:
    defaults = dict(source_url="http://192.168.30.57:1090", poll_seconds=5,
                    timeout_seconds=4, stale_seconds=20, expire_seconds=60,
                    history_minutes=60, history_mb=32, max_response_mb=8,
                    site_name="Local aircraft", map_type="osm")

    def __init__(self, options=None):
        self.__dict__.update(self.defaults | (options or {}))
        p = urllib.parse.urlsplit(self.source_url)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ValueError("source_url must be an HTTP(S) base URL without credentials, query or fragment")
        if p.port is not None and not 1 <= p.port <= 65535:
            raise ValueError("invalid port")
        self.source_url = self.source_url.rstrip("/")
        for key, lo, hi in (("poll_seconds", 2, 60), ("timeout_seconds", 1, 30),
                            ("stale_seconds", 5, 300), ("expire_seconds", 10, 900),
                            ("history_minutes", 1, 480), ("history_mb", 1, 256),
                            ("max_response_mb", 1, 32)):
            value = getattr(self, key)
            if not number(value) or not lo <= value <= hi:
                raise ValueError(f"invalid {key}")
        if self.stale_seconds < self.poll_seconds * 2 or self.expire_seconds <= self.stale_seconds:
            raise ValueError("stale_seconds must be >= 2 polls; expire_seconds must exceed stale_seconds")
        if self.map_type not in ("osm", "carto_dark_all", "carto_light_all", "esri", "blank"):
            raise ValueError("invalid map_type")
        if not isinstance(self.site_name, str) or len(self.site_name) > 100:
            raise ValueError("invalid site_name")


class Fetcher:
    def __init__(self, settings):
        self.settings = settings
        self.bytes = 0
        self.requests = 0
        self.encoding = "unknown"

    def get(self, path):
        p = urllib.parse.urlsplit(self.settings.source_url + path)
        conn_type = http.client.HTTPSConnection if p.scheme == "https" else http.client.HTTPConnection
        conn = conn_type(p.hostname, p.port, timeout=self.settings.timeout_seconds)
        limit = int(self.settings.max_response_mb * 1024 * 1024)
        start = time.monotonic()
        self.requests += 1
        try:
            conn.request("GET", p.path, headers={"Accept-Encoding": "gzip", "Accept": "application/json",
                                                "User-Agent": "HA-tar1090/0.1"})
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError(f"upstream HTTP {response.status}")
            encoding = response.getheader("Content-Encoding", "identity").lower().strip()
            if encoding not in ("gzip", "identity"):
                raise ValueError("unsupported response encoding")
            self.encoding = encoding
            data = bytearray()
            while True:
                remaining = self.settings.timeout_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError("response deadline exceeded")
                if conn.sock:
                    conn.sock.settimeout(remaining)
                elif response.fp and hasattr(response.fp.raw, '_sock'):
                    response.fp.raw._sock.settimeout(remaining)
                block = response.read1(min(65536, limit + 1 - len(data)))
                self.bytes += len(block)
                data.extend(block)
                if len(data) > limit:
                    raise ValueError("encoded response too large")
                if not block:
                    break
            if encoding == "gzip":
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                data = decoder.decompress(data, limit + 1)
                if len(data) > limit or not decoder.eof or decoder.unused_data:
                    raise ValueError("invalid or oversized gzip response")
            return json.loads(data, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        finally:
            conn.close()


def validate(data):
    if not isinstance(data, dict) or not number(data.get("now")) or data["now"] <= 0:
        raise ValueError("missing source timestamp")
    aircraft = data.get("aircraft")
    if not isinstance(aircraft, list) or len(aircraft) > 50000:
        raise ValueError("invalid aircraft list")
    for ac in aircraft:
        if not isinstance(ac, dict) or not isinstance(ac.get("hex"), str):
            raise ValueError("invalid aircraft identity")
        if not 1 <= len(ac["hex"]) <= 16:
            raise ValueError("invalid aircraft identity")
        for field in ("seen", "seen_pos"):
            if field in ac and (not number(ac[field]) or ac[field] < 0):
                raise ValueError("invalid aircraft age")
        for field, bound in (("lat", 90), ("lon", 180)):
            if field in ac and (not number(ac[field]) or abs(ac[field]) > bound):
                raise ValueError("invalid coordinate")
    encode(data)  # Also rejects nonfinite values anywhere in the response.
    return data


class State:
    def __init__(self, settings, clock=time.monotonic, wall=time.time):
        self.settings, self.clock, self.wall = settings, clock, wall
        self.lock = threading.RLock()
        self.started = clock()
        self.epoch = uuid.uuid4().hex
        self.sequence = 0
        self.current = None
        self.accepted_at = None
        self.received_at = None
        self.source_age_at_accept = 0
        self.last_http = None
        self.last_error = None
        self.failures = 0
        self.metadata = {}
        self.sealed = collections.deque()
        self.pending = []
        self.pending_since = None
        self.history_bytes = 0
        self.fetcher = None
        self.worker_tick = clock()

    def receiver(self):
        result = dict(version="HA snapshot bridge", refresh=self.settings.poll_seconds * 1000,
                      history=0, readsb=True, binCraft=False, zstd=False, dbServer=False,
                      haveTraces=False, haveReplay=False)
        result.update(self.metadata)
        return result

    def metadata_update(self, data):
        if not isinstance(data, dict):
            raise ValueError("invalid receiver metadata")
        result = {}
        for key, bound in (("lat", 90), ("lon", 180)):
            if number(data.get(key)) and abs(data[key]) <= bound:
                result[key] = data[key]
        if len(result) != 2:
            raise ValueError("receiver coordinates unavailable")
        with self.lock:
            self.metadata = result

    def accept(self, data):
        validate(data)
        if data["now"] > self.wall() + 60:
            raise ValueError("receiver clock is ahead by more than 60 seconds")
        with self.lock:
            self.last_http = self.clock()
            self.last_error = None
            self.failures = 0
            if self.current and data["now"] == self.current["now"]:
                return False
            if self.current and data["now"] < self.current["now"]:
                self.epoch = uuid.uuid4().hex
                self.sealed.clear()
                self.pending.clear()
                self.history_bytes = 0
            self.current = data
            self.sequence += 1
            self.accepted_at = self.clock()
            self.received_at = self.wall()
            self.source_age_at_accept = max(0, self.wall() - data["now"])
            snapshot = {"now": data["now"], "aircraft": data["aircraft"], "messages": data.get("messages", 0)}
            if not self.pending:
                self.pending_since = self.clock()
            self.pending.append(snapshot)
            # Bound even a single large in-progress chunk.
            if len(self.pending) >= 12 or len(encode({"files": self.pending})) > self.settings.history_mb * 1024 * 512:
                payload = gzip.compress(encode({"files": self.pending}), mtime=0)
                name = f"chunk_{self.epoch}_{self.sequence}.gz"
                self.sealed.append((name, self.clock(), payload))
                self.history_bytes += len(payload)
                self.pending = []
            self.prune()
            return True

    def prune(self):
        cutoff = self.clock() - self.settings.history_minutes * 60
        pending_size = len(encode({"files": self.pending}))
        while self.sealed and (self.sealed[0][1] < cutoff or
                              self.history_bytes + pending_size > self.settings.history_mb * 1024 * 1024):
            _, _, payload = self.sealed.popleft()
            self.history_bytes -= len(payload)
        if self.pending and self.pending_since < cutoff:
            self.pending.clear()

    def status(self):
        with self.lock:
            age = None if self.accepted_at is None else self.source_age_at_accept + self.clock() - self.accepted_at
            elapsed = max(1, self.clock() - self.started)
            return dict(state="waiting" if age is None else "expired" if age >= self.settings.expire_seconds
                        else "stale" if age >= self.settings.stale_seconds else "live",
                        age_seconds=None if age is None else round(age, 1),
                        epoch=self.epoch, sequence=self.sequence, received_at=self.received_at,
                        source_timestamp=self.current["now"] if self.current else None,
                        last_error=self.last_error, failures=self.failures,
                        receiver_ready=bool(self.metadata),
                        upstream_bytes=self.fetcher.bytes if self.fetcher else 0,
                        upstream_requests=self.fetcher.requests if self.fetcher else 0,
                        upstream_encoding=self.fetcher.encoding if self.fetcher else "unknown",
                        average_body_bits_per_second=round(self.fetcher.bytes * 8 / elapsed, 1) if self.fetcher else 0,
                        history_bytes=self.history_bytes, poll_seconds=self.settings.poll_seconds,
                        expire_seconds=self.settings.expire_seconds)

    def response(self, path):
        with self.lock:
            self.prune()
            if path == "/health":
                healthy = self.clock() - self.worker_tick < max(120, self.settings.timeout_seconds * 3)
                return (200 if healthy else 503), encode({"healthy": healthy}), False
            if path == "/status.json":
                return 200, encode(self.status()), False
            if path == "/data/receiver.json":
                return 200, encode(self.receiver()), False
            if path == "/data/aircraft.json":
                if not self.current:
                    return 503, encode({"error": "Waiting for source"}), False
                return 200, encode(self.current | {"ha_bridge": self.status()}), False
            if path == "/chunks/chunks.json":
                names = [c[0] for c in self.sealed] + ["current_large.gz"]
                return 200, encode({"chunks": names, "chunks_all": names}), False
            if path == "/chunks/current_large.gz":
                return 200, gzip.compress(encode({"files": self.pending}), mtime=0), True
            if path.startswith("/chunks/"):
                for name, _, payload in self.sealed:
                    if path == "/chunks/" + name:
                        return 200, payload, True
                # Evicted immutable chunk: empty history is safe during load/retention race.
                if path.endswith(".gz"):
                    return 200, gzip.compress(encode({"files": []}), mtime=0), True
            if path == "/upintheair.json":
                return 200, encode({"rings": []}), False
            return 404, encode({"error": "Not found"}), False


def collect(state, stop, fetcher=None):
    fetcher = fetcher or Fetcher(state.settings)
    state.fetcher = fetcher
    next_metadata = 0
    while not stop.is_set():
        state.worker_tick = state.clock()
        try:
            if state.clock() >= next_metadata:
                try:
                    state.metadata_update(fetcher.get("/data/receiver.json"))
                    next_metadata = state.clock() + 3600
                except (OSError, ValueError, http.client.HTTPException):
                    next_metadata = state.clock() + 60
            state.accept(fetcher.get("/data/aircraft.json"))
        except (OSError, ValueError, http.client.HTTPException) as error:
            with state.lock:
                state.failures += 1
                # Exception text can contain credentials/response fragments: emit category only.
                state.last_error = type(error).__name__
        state.worker_tick = state.clock()
        delay = min(60, state.settings.poll_seconds * 2 ** min(state.failures, 4))
        stop.wait(delay)

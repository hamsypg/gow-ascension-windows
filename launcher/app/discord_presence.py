"""Discord Rich Presence: while the game runs, shows its name and how long
it has been running on the player's Discord profile. Nothing else is sent
(no level, no screenshot). Off by default (the "Discord Rich Presence"
setting under Advanced); talks to the local Discord client directly over
its IPC channel, so no extra package is needed.

Discord's IPC is a local pipe (Windows) or Unix socket (macOS/Linux) at a
well-known path, carrying length-prefixed JSON frames: a handshake, then an
app-chosen command such as SET_ACTIVITY. This is Discord's own public,
documented protocol; nothing here comes from another project's code."""

import json
import os
import socket
import struct
import sys
import threading
import time
import uuid

WINDOWS = sys.platform == 'win32'

# Ascension's own Discord application id (Discord Developer Portal). Empty
# until one is registered: Presence.start() is then a silent no-op.
CLIENT_ID = '1562578669841682582'

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = range(5)
FRAME_HEADER = struct.Struct('<II')      # opcode, body length
RECONNECT_SECONDS = 15                   # how long to wait before trying Discord again
STOP_TIMEOUT = 3                         # stop() waits this long for the thread to end
POLL_SECONDS = 0.05                      # how often a blocked read re-checks "stop"


def _encode(opcode, payload):
    body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    return FRAME_HEADER.pack(opcode, len(body)) + body


class _WindowsPipe:
    """\\\\.\\pipe\\discord-ipc-N, read without blocking (PeekNamedPipe) so a
    stalled Discord client cannot hang the presence thread."""

    def __init__(self, path):
        import ctypes
        import msvcrt
        self._file = open(path, 'r+b', buffering=0)
        self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self._handle = ctypes.c_void_p(msvcrt.get_osfhandle(self._file.fileno()))
        PIPE_NOWAIT = 0x00000001
        mode = ctypes.c_ulong(PIPE_NOWAIT)
        if not self._kernel32.SetNamedPipeHandleState(self._handle, ctypes.byref(mode), None, None):
            self._file.close()
            raise OSError(ctypes.get_last_error(), 'SetNamedPipeHandleState failed')

    def send(self, data):
        if self._file.write(data) != len(data):
            raise ConnectionError('the Discord pipe did not accept the frame')

    def recv(self, size, stop):
        import ctypes
        available = ctypes.c_ulong()
        while not stop.is_set():
            if not self._kernel32.PeekNamedPipe(self._handle, None, 0, None, ctypes.byref(available), None):
                raise OSError(ctypes.get_last_error(), 'PeekNamedPipe failed')
            if available.value:
                return self._file.read(min(size, available.value))
            stop.wait(POLL_SECONDS)
        return b''

    def close(self):
        self._file.close()


class _UnixSocket:
    """The Discord IPC socket on macOS/Linux."""

    def __init__(self, path):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(POLL_SECONDS)
        try:
            self._sock.connect(path)
        except OSError:
            self._sock.close()
            raise

    def send(self, data):
        self._sock.sendall(data)

    def recv(self, size, stop):
        while not stop.is_set():
            try:
                return self._sock.recv(size)
            except socket.timeout:
                continue
        return b''

    def close(self):
        self._sock.close()


def _candidate_paths():
    if WINDOWS:
        return [rf'\\.\pipe\discord-ipc-{i}' for i in range(10)]
    bases = [os.environ.get(v) for v in ('XDG_RUNTIME_DIR', 'TMPDIR', 'TMP', 'TEMP')] + ['/tmp']
    paths = []
    for base in dict.fromkeys(b for b in bases if b):
        for sub in ('', 'app/com.discordapp.Discord', 'snap.discord'):
            for i in range(10):
                paths.append(os.path.join(base, sub, f'discord-ipc-{i}'))
    return paths


def _connect(stop):
    kind = _WindowsPipe if WINDOWS else _UnixSocket
    for path in _candidate_paths():
        if stop.is_set():
            return None
        try:
            return kind(path)
        except OSError:
            continue
    return None


def _recv_exact(conn, size, stop):
    buf = bytearray()
    while len(buf) < size:
        if stop.is_set():
            raise ConnectionAbortedError('stopping')
        chunk = conn.recv(size - len(buf), stop)
        if not chunk:
            raise ConnectionError('Discord closed the connection')
        buf += chunk
    return bytes(buf)


def _read_frame(conn, stop):
    while True:
        opcode, length = FRAME_HEADER.unpack(_recv_exact(conn, FRAME_HEADER.size, stop))
        body = _recv_exact(conn, length, stop) if length else b''
        if opcode == OP_PING:
            conn.send(FRAME_HEADER.pack(OP_PONG, len(body)) + body)
            continue
        if opcode == OP_PONG:
            continue
        if opcode == OP_CLOSE:
            raise ConnectionError('Discord closed the connection')
        if opcode != OP_FRAME:
            raise ValueError('unexpected Discord opcode')
        return json.loads(body) if body else {}


class Presence:
    """start() while the game is running, stop() when it ends (or the
    launcher closes). Both are harmless to call with no client id configured
    or no Discord client running: the thread quietly gives up."""

    def __init__(self, client_id=None):
        self.client_id = client_id or CLIENT_ID
        self._stop = threading.Event()
        self._thread = None
        self._started_at = None

    def start(self):
        if not self.client_id or self._thread:
            return
        self._started_at = int(time.time())
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='discord-presence', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(STOP_TIMEOUT)
        self._thread = None

    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
            except (OSError, ValueError):
                pass
            if not self._stop.is_set():
                self._stop.wait(RECONNECT_SECONDS)

    def _session(self):
        conn = _connect(self._stop)
        if conn is None:
            return
        try:
            conn.send(_encode(OP_HANDSHAKE, {'v': 1, 'client_id': self.client_id}))
            if _read_frame(conn, self._stop).get('evt') != 'READY':
                return
            self._set_activity(conn, {'timestamps': {'start': self._started_at}})
            while not self._stop.is_set():
                _read_frame(conn, self._stop)
        finally:
            try:
                if self._stop.is_set():
                    self._set_activity(conn, None)
                    conn.send(_encode(OP_CLOSE, {}))
            except (OSError, ValueError):
                pass
            conn.close()

    def _set_activity(self, conn, activity):
        args = {'pid': os.getpid()}
        if activity is not None:
            args['activity'] = activity
        conn.send(_encode(OP_FRAME, {'cmd': 'SET_ACTIVITY', 'args': args, 'nonce': str(uuid.uuid4())}))
        _read_frame(conn, self._stop)

"""Checks launcher/app/discord_presence.py against a fake local Discord IPC
server, so the handshake / SET_ACTIVITY / clean shutdown exchange is caught
by something other than running the real launcher with a real Discord open.

Windows' named-pipe transport is not exercised here (this runs on whatever
platform CI or the developer is on); the Unix-socket transport used on
macOS/Linux speaks the same frame protocol, so this still catches a broken
handshake, a wrong opcode, or a stop() that does not clear the activity.

Run with: python -m unittest tests.test_discord_presence -v
"""
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'launcher'))

import app.discord_presence as dp  # noqa: E402

HEADER = struct.Struct('<II')


class FakeDiscord:
    """A minimal stand-in for the local Discord client: accepts one
    connection, answers the handshake and every SET_ACTIVITY, and records
    every frame it received."""

    def __init__(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'discord-ipc-0')
        self.events = []
        self.ready = threading.Event()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        os.environ['XDG_RUNTIME_DIR'] = self.dir
        self.thread.start()
        if not self.ready.wait(2):
            raise TimeoutError('fake Discord server did not come up')

    def _run(self):
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.path)
        srv.listen(1)
        self.ready.set()
        srv.settimeout(5)
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            return
        conn.settimeout(5)
        try:
            while True:
                opcode, payload = self._read(conn)
                self.events.append((opcode, payload))
                if opcode == dp.OP_HANDSHAKE:
                    self._send(conn, dp.OP_FRAME, {'evt': 'READY'})
                elif opcode == dp.OP_FRAME and payload.get('cmd') == 'SET_ACTIVITY':
                    self._send(conn, dp.OP_FRAME, {'evt': None, 'data': {}})
                elif opcode == dp.OP_CLOSE:
                    break
        except (OSError, socket.timeout, ConnectionError):
            pass
        finally:
            conn.close()
            srv.close()
            self.done.set()

    @staticmethod
    def _read(conn):
        header = b''
        while len(header) < HEADER.size:
            chunk = conn.recv(HEADER.size - len(header))
            if not chunk:
                raise ConnectionError
            header += chunk
        opcode, length = HEADER.unpack(header)
        body = b''
        while len(body) < length:
            chunk = conn.recv(length - len(body))
            if not chunk:
                raise ConnectionError
            body += chunk
        return opcode, (json.loads(body) if body else {})

    @staticmethod
    def _send(conn, opcode, payload):
        body = json.dumps(payload).encode('utf-8')
        conn.sendall(HEADER.pack(opcode, len(body)) + body)


@unittest.skipIf(sys.platform == 'win32', 'exercises the Unix-socket transport')
class TestDiscordPresence(unittest.TestCase):
    def test_handshake_then_activity_then_clear_on_stop(self):
        server = FakeDiscord()
        server.start()
        try:
            presence = dp.Presence(client_id='123456789012345678')
            presence.start()
            self.assertTrue(presence._thread is not None)
            # Wait for the handshake and the first SET_ACTIVITY to arrive.
            for _ in range(100):
                if len(server.events) >= 2:
                    break
                time.sleep(0.05)
            presence.stop()
            server.done.wait(2)
        finally:
            pass

        kinds = [opcode for opcode, _ in server.events]
        self.assertIn(dp.OP_HANDSHAKE, kinds, 'no handshake reached the fake Discord client')
        activities = [p for op, p in server.events if op == dp.OP_FRAME and p.get('cmd') == 'SET_ACTIVITY']
        self.assertGreaterEqual(len(activities), 1, 'no SET_ACTIVITY reached the fake Discord client')
        self.assertIn('timestamps', activities[0]['args']['activity'])
        # stop() should clear the activity (no "activity" key) before closing.
        cleared = [a for a in activities if 'activity' not in a['args']]
        self.assertTrue(cleared, 'stop() did not clear the Discord activity')

    def test_start_without_client_id_is_a_no_op(self):
        presence = dp.Presence(client_id='')
        presence.start()
        self.assertIsNone(presence._thread)
        presence.stop()  # must not raise with nothing running


if __name__ == '__main__':
    unittest.main()

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.buffer = b""
        self.commands = []
        self.ready = True
        self.position = -1
        self.on_get = b""
        self.reply = True
        self.closed = False
        self.write_error = False

    @property
    def in_waiting(self):
        return len(self.buffer)

    def read(self, n):
        result, self.buffer = self.buffer[:n], self.buffer[n:]
        return result

    def write(self, payload):
        if self.write_error:
            raise OSError("disconnected")
        self.commands.append(payload)
        if self.reply:
            if payload == b"initialized;":
                self.buffer += b"true\n" if self.ready else b"false\n"
            elif payload == b"get;":
                self.buffer += self.on_get + ("length:%d\n" % self.position).encode()
                self.on_get = b""
        return len(payload)

    def close(self):
        self.closed = True


def load_library():
    path = Path(__file__).resolve().parents[1] / "bamboo_actuator" / "client.py"
    spec = importlib.util.spec_from_file_location("bsa_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=FakeSerial)}):
        spec.loader.exec_module(module)
    return module


library = load_library()



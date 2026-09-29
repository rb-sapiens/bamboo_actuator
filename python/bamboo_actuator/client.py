# -*- coding: utf-8 -*-
import sys
import threading
import time

import serial

_clock = getattr(time, "monotonic", time.time)


class BambooActuator:
    def __init__(self, port, baud, model=None):
        self.ser = serial.Serial(port, baud, timeout=0, write_timeout=1)
        self.timeout = 120
        self.timeout_get = 1
        self.model = model
        self.last_error = None
        self._lock = threading.RLock()
        self._buffer = b""
        self._replies = {}
        self._moving = False
        self._completion_ready = False
        self._move_error = None
        self._move_started = None

    @property
    def moving(self):
        return self._moving

    def signal_handler(self, signal, frame):
        self.close()
        sys.exit(0)

    def _write(self, message):
        try:
            payload = message.encode("ascii")
            if self.ser.write(payload) != len(payload):
                raise IOError("Incomplete serial write")
            return True
        except Exception as exc:
            self.last_error = "serial: {}".format(exc)
            return None

    def _read_messages(self):
        try:
            available = self.ser.in_waiting
            if available:
                self._buffer += self.ser.read(min(available, 4096))
            while b"\n" in self._buffer:
                raw, self._buffer = self._buffer.split(b"\n", 1)
                message = raw.strip().decode("ascii")
                if message.startswith("length:"):
                    self._replies["length"] = int(message[len("length:"):])
                elif message in ("true", "false"):
                    self._replies["initialized"] = message == "true"
                elif message == "success":
                    if self._moving:
                        self._moving = False
                        self._completion_ready = True
                elif message.startswith("error:"):
                    self.last_error = message[len("error:"):]
                    if self._moving:
                        self._moving = False
                        self._completion_ready = False
                        self._move_error = self.last_error
            if len(self._buffer) > 4096:
                self._buffer = b""
                raise ValueError("Serial response too long")
            return True
        except Exception as exc:
            self.last_error = "serial response: {}".format(exc)
            if self._moving:
                self._move_error = self.last_error
            return None

    def _query(self, command, reply):
        self.last_error = None
        if self._read_messages() is None:
            return None
        self._replies.pop(reply, None)
        if self._write(command) is None:
            return None
        deadline = _clock() + self.timeout_get
        while _clock() < deadline:
            if self._read_messages() is None:
                return None
            if reply in self._replies:
                return self._replies.pop(reply)
            time.sleep(0.005)
        self.last_error = "timeout: {}".format(command.rstrip(";"))
        return None

    def set_length(self, length):
        with self._lock:
            self.last_error = None
            try:
                value = int(length)
                if value != length or not 0 <= value <= 4000:
                    raise ValueError("length must be an integer in 0..4000 mm")
            except (TypeError, ValueError, OverflowError) as exc:
                self.last_error = str(exc)
                return None
            if self._read_messages() is None:
                return None
            if self._moving:
                self.last_error = "busy: stop or complete the current movement first"
                return None
            ready = self._query("initialized;", "initialized")
            if ready is not True:
                if ready is False:
                    self.last_error = "not_initialized"
                return None
            self._completion_ready = False
            self._move_error = None
            if self._write("set:{};".format(value)) is None:
                return None
            self._moving = True
            self._move_started = _clock()
            return True

    def get_length(self):
        with self._lock:
            return self._query("get;", "length")

    def initialized(self):
        with self._lock:
            return self._query("initialized;", "initialized")

    def poll_completion(self):
        with self._lock:
            if self._read_messages() is None:
                return None
            if self._move_error is not None:
                self.last_error = self._move_error
                return None
            if self._completion_ready:
                self._completion_ready = False
                return True
            if self._moving and _clock() - self._move_started >= self.timeout:
                reason = "timeout: movement completion"
                if self._write("stop;") is None:
                    reason += "; " + self.last_error
                self._moving = False
                self._move_error = self.last_error = reason
                return None
            return False

    def wait_until_complete(self, timeout=None):
        with self._lock:
            if not (self._moving or self._completion_ready or self._move_error):
                self.last_error = "no pending movement"
                return None
        deadline = _clock() + (self.timeout if timeout is None else timeout)
        while True:
            result = self.poll_completion()
            if result is True or result is None:
                return result
            if _clock() >= deadline:
                with self._lock:
                    reason = "timeout: wait_until_complete"
                    if self._write("stop;") is None:
                        reason += "; " + self.last_error
                    self._moving = False
                    self._move_error = self.last_error = reason
                return None
            with self._lock:
                if not self._moving:
                    self.last_error = "movement cancelled"
                    return None
            time.sleep(0.01)

    def _cancel_tracking(self):
        self._moving = False
        self._completion_ready = False
        self._move_error = None
        self._move_started = None

    def stop(self):
        with self._lock:
            self.last_error = None
            self._cancel_tracking()
            return self._write("stop;")

    def reset(self):
        with self._lock:
            self.last_error = None
            self._cancel_tracking()
            return self._write("reset;")

    def close(self):
        with self._lock:
            self._cancel_tracking()
            try:
                self.ser.close()
                return True
            except Exception as exc:
                self.last_error = "serial close: {}".format(exc)
                return None

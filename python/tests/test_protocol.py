import unittest
from unittest.mock import patch
from serial_support import library


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.ba = library.BambooActuator("fake", 115200)

    def test_debug_logs_do_not_interfere_with_protocol(self):
        self.ba.set_length(100)
        self.ba.ser.on_get = (b"#DEBUG NOT_FOR_DELIVERY profile=1\n"
                              b"#DEBUG mm=-1 target=100 dir=1 homed=1\n"
                              b"success\n#DEBUG pwm=180,240\n")
        self.assertEqual(self.ba.get_length(), -1)
        self.assertIs(self.ba.poll_completion(), True)
        self.assertIsNone(self.ba.last_error)

    def test_negative_measurement_is_not_error(self):
        self.assertEqual(self.ba.get_length(), -1)
        self.assertIsNone(self.ba.last_error)

    def test_query_timeout_is_none(self):
        self.ba.ser.reply = False
        self.ba.timeout_get = 0
        self.assertIsNone(self.ba.get_length())
        self.assertIn("timeout", self.ba.last_error)
        self.assertIsNone(self.ba.initialized())

    def test_initialization_false_is_not_none(self):
        self.ba.ser.ready = False
        self.assertIs(self.ba.initialized(), False)
        self.assertIsNone(self.ba.set_length(100))
        self.assertNotIn(b"set:100;", self.ba.ser.commands)

    def test_completion_during_position_query_is_retained_once(self):
        self.assertIs(self.ba.set_length(100), True)
        self.ba.ser.on_get = b"success\n"
        self.assertEqual(self.ba.get_length(), -1)
        self.assertIs(self.ba.poll_completion(), True)
        self.assertIs(self.ba.poll_completion(), False)

    def test_fragmented_success_and_length(self):
        self.ba.set_length(100)
        self.ba.ser.buffer += b"suc"
        self.assertIs(self.ba.poll_completion(), False)
        self.ba.ser.buffer += b"cess\r\nlength:-1\n"
        self.assertIs(self.ba.poll_completion(), True)
        self.assertEqual(self.ba._replies["length"], -1)

    def test_completion_during_initialized_query(self):
        self.ba.set_length(100)
        self.ba.ser.buffer += b"success\n"
        self.assertIs(self.ba.initialized(), True)
        self.assertIs(self.ba.poll_completion(), True)

    def test_firmware_error_is_none(self):
        self.ba.set_length(100)
        self.ba.ser.buffer += b"error:stalled\n"
        self.assertIsNone(self.ba.poll_completion())
        self.assertEqual(self.ba.last_error, "stalled")

    def test_busy_does_not_replace_move(self):
        self.ba.set_length(100)
        self.assertIsNone(self.ba.set_length(200))
        self.assertNotIn(b"set:200;", self.ba.ser.commands)
        self.ba.ser.buffer += b"success\n"
        self.assertIs(self.ba.poll_completion(), True)

    def test_stop_then_set_discards_old_completion(self):
        self.ba.set_length(100)
        self.ba.stop()
        self.ba.ser.buffer += b"success\nerror:stopped\n"
        self.assertIs(self.ba.set_length(200), True)
        self.assertIs(self.ba.poll_completion(), False)
        self.ba.ser.buffer += b"success\n"
        self.assertIs(self.ba.poll_completion(), True)
        self.assertEqual(self.ba.ser.commands[-3:],
                         [b"stop;", b"initialized;", b"set:200;"])

    def test_move_timeout_requests_stop(self):
        self.ba.set_length(100)
        self.ba._move_started -= self.ba.timeout + 1
        self.assertIsNone(self.ba.poll_completion())
        self.assertEqual(self.ba.ser.commands[-1], b"stop;")
        self.assertIn("timeout", self.ba.last_error)

    def test_wait_success_and_timeout(self):
        self.ba.set_length(100)
        self.ba.ser.buffer += b"success\n"
        self.assertIs(self.ba.wait_until_complete(), True)
        self.ba.set_length(200)
        self.assertIsNone(self.ba.wait_until_complete(timeout=0))
        self.assertEqual(self.ba.ser.commands[-1], b"stop;")

    def test_invalid_targets_do_not_move(self):
        for value in (-1, 4001, 1.5, "bad", None):
            self.assertIsNone(self.ba.set_length(value))
        self.assertEqual(self.ba.ser.commands, [])

    def test_serial_and_decode_failures_are_none(self):
        self.ba.ser.buffer = b"length:bad\n"
        self.assertIsNone(self.ba.get_length())
        self.ba.ser.write_error = True
        self.assertIsNone(self.ba.stop())
        self.assertIsNone(self.ba.get_length())

    def test_client_does_not_replace_signal_handler(self):
        with patch("signal.signal") as handler:
            library.BambooActuator("fake", 115200)
            handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()

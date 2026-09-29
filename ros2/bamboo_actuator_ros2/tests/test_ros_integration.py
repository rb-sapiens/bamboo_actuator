import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
support_spec = importlib.util.spec_from_file_location(
    "bamboo_serial_support", ROOT / "python/tests/serial_support.py")
support = importlib.util.module_from_spec(support_spec)
support_spec.loader.exec_module(support)
library = support.library


class Message:
    def __init__(self, data=None):
        self.data = data


class Publisher:
    def __init__(self):
        self.values = []

    def publish(self, msg):
        self.values.append(msg.data)


class NodeStub:
    def __init__(self, name):
        self.params = {}
        self.log = []
        self.subscriptions = {}

    def declare_parameter(self, name, default):
        self.params[name] = default

    def get_parameter(self, name):
        return types.SimpleNamespace(value=self.params[name])

    def create_publisher(self, *args):
        return Publisher()

    def create_subscription(self, msg_type, topic, callback, qos):
        self.subscriptions[topic] = callback
        return callback

    def create_timer(self, *args):
        return None

    def get_logger(self):
        return types.SimpleNamespace(info=self.log.append, warn=self.log.append,
                                     error=self.log.append)


node_path = (ROOT / "ros2" / "bamboo_actuator_ros2" /
             "bamboo_actuator_ros2" / "bamboo_actuator_node.py")


class RosIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.modules = patch.dict(sys.modules, {
            "rclpy": types.ModuleType("rclpy"),
            "rclpy.node": types.SimpleNamespace(Node=NodeStub),
            "std_msgs": types.ModuleType("std_msgs"),
            "std_msgs.msg": types.SimpleNamespace(Bool=Message, Int16=Message,
                                                  Int32=Message, String=Message),
            "unitree_go": types.ModuleType("unitree_go"),
            "unitree_go.msg": types.SimpleNamespace(WirelessController=Message),
            "bamboo_actuator": library,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location("node_under_test", node_path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.exists = patch.object(self.module.os.path, "exists", return_value=True)
        self.exists.start()
        self.addCleanup(self.exists.stop)
        self.node = self.module.BambooActuatorNode()

    def start_move(self, length=100):
        self.node.subscriptions["/bamboo_actuator/set_length"](Message(length))
        self.node._next_query = 0
        self.node._poll_actuator()
        return self.node._actuator

    def test_end_to_end_negative_position_and_completion(self):
        ba = self.start_move()
        self.assertTrue(ba.moving)
        self.assertEqual(self.node._status, "moving")
        ba.ser.on_get = b"success\n"
        self.node._next_query = 0
        self.node._poll_actuator()
        self.assertEqual(self.node._length_pub.values[-1], -1)
        self.assertEqual(self.node._error_pub.values, [])
        self.node._poll_actuator()
        self.assertEqual(self.node._complete_pub.values, [False, True])
        self.assertEqual(self.node._status, "completed")
        self.node._poll_actuator()
        self.assertEqual(self.node._complete_pub.values, [False, True])

    def test_connection_reused_and_old_success_not_misattributed(self):
        ba = self.start_move()
        ba.ser.buffer += b"success\n"
        self.node._on_set_length(Message(200))
        self.node._poll_actuator()
        self.assertIs(self.node._actuator, ba)
        self.assertEqual(self.node._complete_pub.values, [False, False])
        self.assertEqual(self.node._active_length, 200)
        self.assertEqual(ba.ser.commands[-2:], [b"initialized;", b"set:200;"])
        ba.ser.buffer += b"success\n"
        self.node._poll_actuator()
        self.assertEqual(self.node._complete_pub.values[-1], True)

    def test_stop_during_initialization_cancels_queued_move(self):
        self.node._on_set_length(Message(100))
        ba = self.node._actuator
        ba.ser.ready = False
        self.node._next_query = 0
        self.node._poll_actuator()
        self.assertFalse(ba.moving)
        self.node.subscriptions["/bamboo_actuator/stop"](Message(True))
        ba.ser.ready = True
        self.node._next_query = 0
        self.node._poll_actuator()
        self.assertNotIn(b"set:100;", ba.ser.commands)
        self.assertEqual(self.node._status, "stopped")

    def test_stop_topic_cancels_move_and_discards_late_completion(self):
        ba = self.start_move()
        self.node.subscriptions["/bamboo_actuator/stop"](Message(True))
        self.assertEqual(ba.ser.commands[-1], b"stop;")
        self.assertFalse(ba.moving)
        self.assertIsNone(self.node._active_length)
        self.assertIsNone(self.node._pending_length)
        ba.ser.buffer += b"success\n"
        self.node._poll_actuator()
        self.assertEqual(self.node._status, "stopped")
        self.assertNotIn(True, self.node._complete_pub.values)

    def test_stop_topic_false_leaves_move_running(self):
        ba = self.start_move()
        before = list(ba.ser.commands)
        self.node.subscriptions["/bamboo_actuator/stop"](Message(False))
        self.assertEqual(ba.ser.commands, before)
        self.assertTrue(ba.moving)
        self.assertEqual(self.node._status, "moving")

    def test_stop_topic_write_failure_reports_error(self):
        ba = self.start_move()
        ba.ser.write_error = True
        self.node.subscriptions["/bamboo_actuator/stop"](Message(True))
        self.assertEqual(self.node._status, "error")
        self.assertTrue(self.node._error_pub.values)
        self.assertTrue(ba.ser.closed)
        self.assertNotIn(True, self.node._complete_pub.values)

    def test_stall_publishes_error_and_closes(self):
        ba = self.start_move()
        ba.ser.buffer += b"error:stalled\n"
        self.node._poll_actuator()
        self.assertEqual(self.node._error_pub.values, ["stalled"])
        self.assertEqual(self.node._status, "error")
        self.assertTrue(ba.ser.closed)
        self.assertNotIn(True, self.node._complete_pub.values)

    def test_timeout_stops_and_does_not_publish_fake_position(self):
        ba = self.start_move()
        ba.ser.reply = False
        ba.timeout_get = 0
        self.node._next_query = 0
        self.node._poll_actuator()
        self.assertEqual(self.node._length_pub.values, [])
        self.assertEqual(self.node._status, "error")
        self.assertEqual(ba.ser.commands[-1], b"stop;")

    def test_initialization_timeout(self):
        self.node._on_set_length(Message(100))
        ba = self.node._actuator
        self.node._opened_at -= 61
        self.node._poll_actuator()
        self.assertEqual(self.node._status, "error")
        self.assertNotIn(b"set:100;", ba.ser.commands)

    def test_invalid_target_does_not_open_connection(self):
        self.node._on_set_length(Message(-1))
        self.assertIsNone(self.node._actuator)
        self.assertEqual(len(self.node._error_pub.values), 1)

    def test_wireless_uses_same_connection_and_limits(self):
        self.node.params["max_length"] = 1500
        self.node._on_key_command(self.module.KEY_EXTEND)
        self.node._next_query = 0
        self.node._poll_actuator()
        ba = self.node._actuator
        self.assertIn(b"set:1500;", ba.ser.commands)
        self.node._on_key_command(self.module.KEY_RETRACT)
        self.node._poll_actuator()
        self.assertIs(self.node._actuator, ba)
        self.assertIn(b"set:0;", ba.ser.commands)
        self.node._on_key_command(self.module.KEY_STOP)
        self.assertEqual(self.node._status, "stopped")


if __name__ == "__main__":
    unittest.main()

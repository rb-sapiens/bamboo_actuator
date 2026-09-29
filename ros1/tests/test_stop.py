import importlib.util
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('serial_support', ROOT / 'python/tests/serial_support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


class Message:
    def __init__(self, data):
        self.data = data


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.rospy = Mock()
        self.rospy.Publisher.side_effect = lambda *args, **kwargs: Mock()
        self.rospy.is_shutdown.return_value = True
        self.factory = Mock(side_effect=support.library.BambooActuator)
        modules = {
            'rospy': self.rospy,
            'bamboo_actuator': types.SimpleNamespace(BambooActuator=self.factory),
            'std_msgs': types.ModuleType('std_msgs'),
            'std_msgs.msg': types.SimpleNamespace(Int16=Message, String=Message, Bool=Message),
            'actionlib_msgs': types.ModuleType('actionlib_msgs'),
            'actionlib_msgs.msg': types.SimpleNamespace(GoalStatus=Mock),
        }
        with patch.dict(sys.modules, modules):
            runpy.run_path(str(ROOT / 'ros1/nodes/bsactuator_ros'), run_name='__main__')
        self.callbacks = {call.args[0]: call.args[2]
                          for call in self.rospy.Subscriber.call_args_list}
        self.state = self.callbacks['set_length'].__globals__

    def poll(self):
        self.state['next_query'] = 0
        self.state['publish_get_length']()

    def start(self, length=200):
        self.callbacks['set_length'](Message(length))
        self.poll()
        return self.state['ba']

    def test_startup_stop_and_reset_do_not_connect(self):
        self.poll()
        self.callbacks['/bamboo_actuator/stop'](Message(True))
        self.callbacks['reset'](Message('true'))
        self.factory.assert_not_called()

    def test_missing_device_then_new_command_retries(self):
        self.factory.side_effect = OSError('device missing')
        self.callbacks['set_length'](Message(200))
        self.assertIsNone(self.state['ba'])
        self.assertIsNone(self.state['pending_length'])
        self.rospy.logerr.assert_called()
        self.factory.side_effect = support.library.BambooActuator
        self.poll()
        self.assertEqual(self.factory.call_count, 1)
        ba = self.start(300)
        self.assertEqual(self.factory.call_count, 2)
        self.assertIn(b'set:300;', ba.ser.commands)
        self.assertNotIn(b'set:200;', ba.ser.commands)

    def test_connection_reused_after_completion_and_stop(self):
        ba = self.start()
        ba.ser.buffer += b'success\n'
        self.poll()
        self.state['publisher_goal_status'].publish.assert_called_once()
        self.start(300)
        self.callbacks['/bamboo_actuator/stop'](Message(True))
        self.start(400)
        self.factory.assert_called_once_with('/dev/bamboo_actuator', 115200)
        self.assertIs(self.state['ba'], ba)
        self.assertFalse(ba.ser.closed)

    def test_position_failure_closes_and_next_command_reconnects(self):
        ba = self.start()
        ba.ser.reply = False
        ba.timeout_get = 0
        self.poll()
        self.assertTrue(ba.ser.closed)
        self.assertIsNone(self.state['ba'])
        self.state['publisher_get_length'].publish.assert_not_called()
        self.poll()
        self.assertEqual(self.factory.call_count, 1)
        self.start(300)
        self.assertEqual(self.factory.call_count, 2)

    def test_stop_cancels_completion_tracking(self):
        for topic, value in (('/bamboo_actuator/stop', True), ('stop', 'true')):
            with self.subTest(topic=topic):
                ba = self.start()
                self.callbacks[topic](Message(value))
                self.assertFalse(self.state['moving'])
                self.assertEqual(ba.ser.commands[-1], b'stop;')
                ba.ser.buffer += b'success\n'
                self.poll()
                self.state['publisher_goal_status'].publish.assert_not_called()

    def test_false_does_not_stop(self):
        ba = self.start()
        self.callbacks['/bamboo_actuator/stop'](Message(False))
        self.assertNotIn(b'stop;', ba.ser.commands)
        self.assertTrue(self.state['moving'])

    def test_homing_waits_for_ready_and_keeps_latest_command(self):
        self.callbacks['set_length'](Message(100))
        ba = self.state['ba']
        ba.ser.ready = False
        self.poll()
        self.callbacks['set_length'](Message(200))
        self.assertNotIn(b'set:100;', ba.ser.commands)
        self.assertNotIn(b'set:200;', ba.ser.commands)
        ba.ser.ready = True
        self.poll()
        self.assertIn(b'set:200;', ba.ser.commands)
        self.factory.assert_called_once()

    def test_stop_during_homing_cancels_pending_command(self):
        self.callbacks['set_length'](Message(100))
        ba = self.state['ba']
        self.callbacks['/bamboo_actuator/stop'](Message(True))
        self.poll()
        self.assertNotIn(b'set:100;', ba.ser.commands)

    def test_initialization_timeout_discards_command(self):
        self.callbacks['set_length'](Message(100))
        ba = self.state['ba']
        self.state['opened_at'] -= 61
        self.poll()
        self.assertTrue(ba.ser.closed)
        self.assertIsNone(self.state['pending_length'])
        self.assertNotIn(b'set:100;', ba.ser.commands)

    def test_write_failure_and_exception_close_connection(self):
        for raises in (False, True):
            with self.subTest(raises=raises):
                ba = self.start()
                if raises:
                    ba.stop = Mock(side_effect=OSError('disconnected'))
                else:
                    ba.ser.write_error = True
                self.callbacks['/bamboo_actuator/stop'](Message(True))
                self.assertTrue(ba.ser.closed)
                self.assertIsNone(self.state['ba'])

    def test_shutdown_closes_connection(self):
        ba = self.start()
        self.rospy.on_shutdown.call_args.args[0]()
        self.assertTrue(ba.ser.closed)
        self.assertIsNone(self.state['ba'])

    def test_reset_waits_for_homing_again(self):
        ba = self.start()
        self.callbacks['reset'](Message('true'))
        self.assertEqual(ba.ser.commands[-1], b'reset;')
        self.assertIsNone(self.state['pending_length'])
        self.assertFalse(self.state['ready'])
        self.assertFalse(self.state['moving'])


if __name__ == '__main__':
    unittest.main()

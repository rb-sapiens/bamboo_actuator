from typing import Optional

import os
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Int16, Int32, String
from unitree_go.msg import WirelessController

KEY_EXTEND = 0x1000
KEY_RETRACT = 0x4000
KEY_STOP = 0x0400


class BambooActuatorNode(Node):
    def __init__(self) -> None:
        super().__init__("bamboo_actuator_node")
        for name, default in (
            ("serial_device", "/dev/bamboo_actuator"),
            ("baud_rate", 115200),
            ("log_keys_on_change", True),
            ("set_length_topic", "/bamboo_actuator/set_length"),
            ("stop_topic", "/bamboo_actuator/stop"),
            ("max_length", 2700),
            ("completion_topic", "/bamboo_actuator/movement_complete"),
            ("length_topic", "/bamboo_actuator/current_length"),
            ("status_topic", "/bamboo_actuator/status"),
            ("error_topic", "/bamboo_actuator/error"),
            ("movement_timeout", 120.0),
            ("initialization_timeout", 60.0),
            ("serial_response_timeout", 0.2),
        ):
            self.declare_parameter(name, default)
        if not 0 <= self.get_parameter("max_length").value <= 4000:
            raise ValueError("max_length must be in 0..4000 mm")
        for name in ("movement_timeout", "initialization_timeout", "serial_response_timeout"):
            if self.get_parameter(name).value <= 0:
                raise ValueError(name + " must be positive")

        self._complete_pub = self.create_publisher(
            Bool, self.get_parameter("completion_topic").value, 10)
        self._length_pub = self.create_publisher(
            Int32, self.get_parameter("length_topic").value, 10)
        self._status_pub = self.create_publisher(
            String, self.get_parameter("status_topic").value, 10)
        self._error_pub = self.create_publisher(
            String, self.get_parameter("error_topic").value, 10)
        self._wireless_sub = self.create_subscription(
            WirelessController, "/wirelesscontroller", self._on_wireless, 10)
        set_length_topic = self.get_parameter("set_length_topic").value
        self._set_length_sub = self.create_subscription(
            Int16, set_length_topic, self._on_set_length, 10)
        stop_topic = self.get_parameter("stop_topic").value
        self._stop_sub = self.create_subscription(
            Bool, stop_topic, self._on_stop, 10)

        self._last_keys: Optional[int] = None
        self._actuator = None
        self._pending_length = None
        self._active_length = None
        self._ready = False
        self._opened_at = 0.0
        self._next_query = 0.0
        self._status = None
        self._timer = self.create_timer(0.1, self._poll_actuator)
        self._publish_status("idle")
        self.get_logger().info(
            f"Subscribed to /wirelesscontroller, {set_length_topic}, and {stop_topic}")

    def _publish_status(self, status):
        if status != self._status:
            self._status = status
            self._status_pub.publish(String(data=status))

    def _close_actuator(self) -> None:
        if self._actuator is None:
            return
        try:
            if self._actuator.stop() is None:
                self.get_logger().warn(
                    f"Stop before close failed: {self._actuator.last_error}")
            if self._actuator.close() is None:
                self.get_logger().warn(
                    f"Close failed: {self._actuator.last_error}")
        except Exception as exc:
            self.get_logger().warn(f"Failed to close BambooActuator: {exc}")
        finally:
            self._actuator = None
            self._ready = False
            self._pending_length = None
            self._active_length = None

    def _fail(self, reason):
        self.get_logger().error(reason)
        self._complete_pub.publish(Bool(data=False))
        self._error_pub.publish(String(data=reason))
        self._publish_status("error")
        self._close_actuator()

    def _open_actuator(self):
        if self._actuator is not None:
            return self._actuator
        import bamboo_actuator

        dev = self.get_parameter("serial_device").value
        baud = self.get_parameter("baud_rate").value
        if not os.path.exists(dev):
            raise FileNotFoundError(f"{dev} does not exist")
        self._actuator = bamboo_actuator.BambooActuator(dev, baud)
        self._actuator.timeout = self.get_parameter("movement_timeout").value
        self._actuator.timeout_get = self.get_parameter("serial_response_timeout").value
        self._ready = False
        self._opened_at = time.monotonic()
        self._next_query = self._opened_at + 2.0
        self.get_logger().info(f"Opened BambooActuator({dev!r}, {baud})")
        return self._actuator

    def _queue_length(self, length):
        max_length = self.get_parameter("max_length").value
        if not 0 <= length <= max_length:
            reason = f"Invalid target {length}; expected 0..{max_length} mm"
            self.get_logger().warn(reason)
            self._error_pub.publish(String(data=reason))
            return
        try:
            ba = self._open_actuator()
            if self._active_length is not None:
                if ba.stop() is None:
                    self._fail(ba.last_error)
                    return
                self._active_length = None
            self._pending_length = length
            self._complete_pub.publish(Bool(data=False))
            self._publish_status("pending" if self._ready else "homing")
        except Exception as exc:
            self._fail(f"Actuator command failed: {exc}")

    def _stop(self):
        self._pending_length = None
        self._active_length = None
        if self._actuator is not None and self._actuator.stop() is None:
            self._fail(self._actuator.last_error)
            return
        self._complete_pub.publish(Bool(data=False))
        self._publish_status("stopped")

    def _on_key_command(self, keys: int) -> None:
        if keys == KEY_EXTEND:
            self._queue_length(min(2000, self.get_parameter("max_length").value))
        elif keys == KEY_RETRACT:
            self._queue_length(0)
        elif keys == KEY_STOP:
            try:
                self._stop()
            except Exception as exc:
                self._fail(f"Actuator stop failed: {exc}")

    def _on_set_length(self, msg: Int16) -> None:
        self._queue_length(int(msg.data))

    def _on_stop(self, msg: Bool) -> None:
        if msg.data:
            self._on_key_command(KEY_STOP)

    def _poll_actuator(self):
        ba = self._actuator
        if ba is None:
            return
        try:
            now = time.monotonic()
            if not self._ready:
                if now - self._opened_at > self.get_parameter("initialization_timeout").value:
                    self._fail("timeout: actuator initialization")
                    return
                if now < self._next_query:
                    return
                self._next_query = now + 0.5
                ready = ba.initialized()
                if ready is not True:
                    return
                self._ready = True
                if self._pending_length is None and self._status != "stopped":
                    self._publish_status("idle")

            result = ba.poll_completion()
            if result is None:
                self._fail(ba.last_error or "Actuator completion failed")
                return
            if result is True and self._active_length is not None:
                self.get_logger().info(f"Movement completed: {self._active_length} mm")
                self._active_length = None
                self._complete_pub.publish(Bool(data=True))
                self._publish_status("completed")

            if self._pending_length is not None:
                length = self._pending_length
                if ba.set_length(length) is None:
                    self._fail(ba.last_error or "Actuator set failed")
                    return
                self._pending_length = None
                self._active_length = length
                self._publish_status("moving")
                self.get_logger().info(f"bamboo_actuator.set_length({length})")

            if now >= self._next_query:
                self._next_query = now + 0.5
                length = ba.get_length()
                if length is None:
                    self._fail(ba.last_error or "Position query failed")
                    return
                self._length_pub.publish(Int32(data=length))
        except Exception as exc:
            self._fail(f"Actuator communication failed: {exc}")

    def _on_wireless(self, msg: WirelessController) -> None:
        keys = int(msg.keys)
        if self.get_parameter("log_keys_on_change").value:
            if self._last_keys is None or keys != self._last_keys:
                self.get_logger().info(
                    f"Wireless keys=0x{keys:04x} ({keys}) lx={msg.lx:.3f} "
                    f"ly={msg.ly:.3f} rx={msg.rx:.3f} ry={msg.ry:.3f}")
        if keys != self._last_keys:
            if keys in (KEY_EXTEND, KEY_RETRACT, KEY_STOP):
                self._on_key_command(keys)
        self._last_keys = keys


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BambooActuatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._close_actuator()
        node.destroy_node()
        rclpy.shutdown()

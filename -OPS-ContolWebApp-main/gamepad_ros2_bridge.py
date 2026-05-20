#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from std_msgs.msg import Float64MultiArray, Int8MultiArray
from sensor_msgs.msg import Joy
import pygame
import time
from evdev import InputDevice, categorize, ecodes, list_devices
import select

class GamepadRos2Bridge(Node):
    # Mapowanie: przypisz kody evdev do tych zmiennych
    pole0_pos = 308  # np. BTN_NORTH (Y)
    pole0_neg = 305  # np. BTN_EAST (B)
    pole1_pos = 307  # np. BTN_SOUTH (A)
    pole1_neg = 304  # np. BTN_WEST (X)
    pole2_pos = (ecodes.ABS_HAT0Y, -1)
    pole2_neg = (ecodes.ABS_HAT0X, 1)
    pole3_pos = (ecodes.ABS_HAT0X, -1)
    pole3_neg = (ecodes.ABS_HAT0Y, 1)
    # HAT obsługa przez evdev: ABS_HAT0X, ABS_HAT0Y
    pole4_pos = 317  # right
    pole4_neg = 318  # left
    pole5_pos = 314  # up
    pole5_neg = 315   # down

    def __init__(self):
        super().__init__('gamepad_ros2_bridge')
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.array_topic_pub = self.create_publisher(Float64MultiArray, '/array_topic', 10)
        self.timer = self.create_timer(0.05, self.timer_callback)  # 20 Hz
        self.last_array = [0]*6
        self.init_gamepad()
        self.button_states = {}  # evdev code: 0/1/2
        self.abs_states = {}     # for HAT
        self.gamepad_publisher = self.create_publisher(Joy, '/gamepad/input', 10)

    def init_gamepad(self):
        # Pygame do osi
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.get_logger().info(f'Gamepad connected (pygame): {self.joystick.get_name()}')
        else:
            self.get_logger().warn('No gamepad detected (pygame)!')
        # evdev do przycisków
        devices = [InputDevice(fn) for fn in list_devices()]
        self.evdev_dev = None
        for dev in devices:
            if 'Gamepad' in dev.name or 'Controller' in dev.name or 'Joystick' in dev.name:
                self.evdev_dev = dev
                self.get_logger().info(f'Gamepad connected (evdev): {dev.name} ({dev.fn})')
                break
        if not self.evdev_dev:
            self.get_logger().warn('No gamepad detected (evdev)!')

    def update_evdev_states(self):
        if not self.evdev_dev:
            return
        r, _, _ = select.select([self.evdev_dev], [], [], 0)
        for dev in r:
            for event in dev.read():
                if event.type == ecodes.EV_KEY:
                    self.button_states[event.code] = event.value
                elif event.type == ecodes.EV_ABS:
                    self.abs_states[event.code] = event.value

    def publish_gamepad_input(self, buttons, axes, hat=(0, 0)):
        # Dodaj paddle'e na końcu listy przycisków
        extended_buttons = buttons + getattr(self, 'paddle_buttons', [])
        msg = Joy()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.axes = axes
        msg.buttons = extended_buttons
        self.gamepad_publisher.publish(msg)
        self.publish_cmd_vel(axes, extended_buttons)

    def get_trigger_scaled(self, code):
        raw = self.abs_states.get(code, 0)
        return (raw / 1023)

    def publish_cmd_vel(self, axes=None, buttons=None):
        if axes is None:
            twist_msg = Twist()
            twist_msg.linear.x = 0.0
            twist_msg.angular.z = 0.0
            self.cmd_vel_pub.publish(twist_msg)
            return

        reverse_mode_left = self.button_states.get(310, None)
        reverse_mode_right = self.button_states.get(311, None)

        left_trigger = self.get_trigger_scaled(10) * (-1 if reverse_mode_left else 1)
        
        right_trigger = self.get_trigger_scaled(9) * (-1 if reverse_mode_right else 1)
       
        twist_msg = Twist()
        twist_msg.linear.x = getattr(self, 'max_linear_speed', 1.0) * (left_trigger + right_trigger) / 2 * getattr(self, 'speed_factor', 1.0)
        twist_msg.angular.z = getattr(self, 'max_angular_speed', 1.0) * -(left_trigger - right_trigger) / 2 * getattr(self, 'speed_factor', 1.0)
        self.cmd_vel_pub.publish(twist_msg)

    def publish_button_states(self, kill_switch, autonomy, manual):
        # Przykład: publikacja Int8MultiArray
        msg = Int8MultiArray()
        msg.data = [manual, autonomy, kill_switch]
        # Dodaj własny publisher jeśli potrzebujesz
        # self.button_publisher.publish(msg)

    def update_speed_factor(self, factor):
        self.speed_factor = factor

    def float_to_byte(self, value):
        value = max(-1.0, min(1.0, value))
        return int((value*127.0)+128)

    def float_to_byte_100(self, value):
        value = max(-100.0, min(100.0, value))
        return int((value + 100.0) / 200.0 * 254)

    def send_serial_frame(self, mark, *bytes):
        try:
            sum = checksum = 0
            for byte in bytes:
                sum += byte
            checksum = sum % 256
            frame = bytearray()
            frame.extend(b"$")
            frame.extend(mark.encode('utf-8'))
            for byte in bytes:
                frame.append(byte)
            frame.append(checksum)
            frame.extend(b"#")
            bit_string = ' '.join(f'{byte:08b}' for byte in frame)
            # print(bit_string)
            # Dodaj obsługę portu szeregowego jeśli potrzebujesz
        except Exception as e:
            print(f"Błąd przy wysyłaniu ramki szeregowej: {e}")

    def timer_callback(self):
        self.update_evdev_states()
        pygame.event.pump()
        if not self.joystick:
            if pygame.joystick.get_count() > 0:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                self.get_logger().info(f'Gamepad connected: {self.joystick.get_name()}')
            else:
                twist_msg = Twist()
                twist_msg.linear.x = 0.0
                twist_msg.angular.z = 0.0
                self.cmd_vel_pub.publish(twist_msg)
                return
        reverse_mode_left = self.button_states.get(310, None)
        reverse_mode_right = self.button_states.get(311, None)
        left_trigger = self.get_trigger_scaled(10) * (-1 if reverse_mode_left else 1)
        right_trigger = self.get_trigger_scaled(9) * (-1 if reverse_mode_right else 1)
        twist_msg = Twist()
        twist_msg.linear.x = getattr(self, 'max_linear_speed', 1.0) * (left_trigger + right_trigger) / 2 * getattr(self, 'speed_factor', 1.0)
        twist_msg.angular.z = getattr(self, 'max_angular_speed', 1.0) * (left_trigger - right_trigger) / 2 * getattr(self, 'speed_factor', 1.0)
        self.cmd_vel_pub.publish(twist_msg)
        array = [0]*6
        # Pole 0
        if isinstance(self.pole0_pos, tuple):
            if self.abs_states.get(self.pole0_pos[0], 0) == self.pole0_pos[1]:
                array[0] = 100
        elif self.pole0_pos is not None and self.button_states.get(self.pole0_pos, 0):
            array[0] = 100
        if isinstance(self.pole0_neg, tuple):
            if self.abs_states.get(self.pole0_neg[0], 0) == self.pole0_neg[1]:
                array[0] = -100
        elif self.pole0_neg is not None and self.button_states.get(self.pole0_neg, 0):
            array[0] = -100
        # Pole 1
        if isinstance(self.pole1_pos, tuple):
            if self.abs_states.get(self.pole1_pos[0], 0) == self.pole1_pos[1]:
                array[1] = 100
        elif self.pole1_pos is not None and self.button_states.get(self.pole1_pos, 0):
            array[1] = 100
        if isinstance(self.pole1_neg, tuple):
            if self.abs_states.get(self.pole1_neg[0], 0) == self.pole1_neg[1]:
                array[1] = -100
        elif self.pole1_neg is not None and self.button_states.get(self.pole1_neg, 0):
            array[1] = -100
        # Pole 2
        if isinstance(self.pole2_pos, tuple):
            if self.abs_states.get(self.pole2_pos[0], 0) == self.pole2_pos[1]:
                array[2] = 100
        elif self.pole2_pos is not None and self.button_states.get(self.pole2_pos, 0):
            array[2] = 100
        if isinstance(self.pole2_neg, tuple):
            if self.abs_states.get(self.pole2_neg[0], 0) == self.pole2_neg[1]:
                array[2] = -100
        elif self.pole2_neg is not None and self.button_states.get(self.pole2_neg, 0):
            array[2] = -100
        # Pole 3
        if isinstance(self.pole3_pos, tuple):
            if self.abs_states.get(self.pole3_pos[0], 0) == self.pole3_pos[1]:
                array[3] = 100
        elif self.pole3_pos is not None and self.button_states.get(self.pole3_pos, 0):
            array[3] = 100
        if isinstance(self.pole3_neg, tuple):
            if self.abs_states.get(self.pole3_neg[0], 0) == self.pole3_neg[1]:
                array[3] = -100
        elif self.pole3_neg is not None and self.button_states.get(self.pole3_neg, 0):
            array[3] = -100
        # Pole 4
        if isinstance(self.pole4_pos, tuple):
            if self.abs_states.get(self.pole4_pos[0], 0) == self.pole4_pos[1]:
                array[4] = 100
        elif self.pole4_pos is not None and self.button_states.get(self.pole4_pos, 0):
            array[4] = 100
        if isinstance(self.pole4_neg, tuple):
            if self.abs_states.get(self.pole4_neg[0], 0) == self.pole4_neg[1]:
                array[4] = -100
        elif self.pole4_neg is not None and self.button_states.get(self.pole4_neg, 0):
            array[4] = -100
        # Pole 5
        if isinstance(self.pole5_pos, tuple):
            if self.abs_states.get(self.pole5_pos[0], 0) == self.pole5_pos[1]:
                array[5] = 100
        elif self.pole5_pos is not None and self.button_states.get(self.pole5_pos, 0):
            array[5] = 100
        if isinstance(self.pole5_neg, tuple):
            if self.abs_states.get(self.pole5_neg[0], 0) == self.pole5_neg[1]:
                array[5] = -100
        elif self.pole5_neg is not None and self.button_states.get(self.pole5_neg, 0):
            array[5] = -100
        # Wysyłaj tylko przy zmianie
        if array != self.last_array:
            msg = Float64MultiArray()
            msg.data = [float(x) for x in array]
            self.array_topic_pub.publish(msg)
            self.get_logger().info(f'Publishing array_topic: {array}')
            self.last_array = array.copy()

def main(args=None):
    rclpy.init(args=args)
    node = GamepadRos2Bridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

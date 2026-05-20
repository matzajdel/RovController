import os
import sys
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32MultiArray

# Add backend to path to import satel_service
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from services.satel_service import build_cmd_vel_full_packet, build_rgb_packet

# Import receiver
from rover_binary_receiver import SerialReceiverNode

class MockReceiverNode(SerialReceiverNode):
    def __init__(self):
        self.published_messages = []
        super().__init__('/dev/null', 9600)

    def _connect_serial(self):
        self.get_logger().info("Mocking serial connection.")

    # Override create_publisher to intercept messages
    def create_publisher(self, msg_type, topic, qos_profile, **kwargs):
        class MockPublisher:
            def __init__(self, parent, t):
                self.parent = parent
                self.topic = t
            def publish(self, msg):
                self.parent.published_messages.append((self.topic, msg))
                print(f"[Opublikowano na {self.topic}]: {msg}")
        return MockPublisher(self, topic)

def main():
    rclpy.init()
    
    print("\n--- TEST: Sprawdzanie kodowania i dekodowania D4 (cmd_vel) oraz RG (rgb) ---")
    
    # Utworzenie zmockowanego node'a
    node = MockReceiverNode()
    
    # 1. Test D4
    print("\n1. Testowanie trybu D4 (cmd_vel) z wartościami: lx=0.5, ly=-0.2, lz=0.5, az=1.0")
    d4_packet = build_cmd_vel_full_packet(0.5, -0.2, 0.5, 1.0)
    print(f"Wygenerowana ramka binarna: {d4_packet.hex()}")
    node._parse_frame(d4_packet)
    
    # 2. Test RG
    print("\n2. Testowanie trybu RG (rgb) z wartościami: r=200, g=50, b=0")
    rg_packet = build_rgb_packet(200.0, 50.0, 0.0)
    print(f"Wygenerowana ramka binarna: {rg_packet.hex()}")
    node._parse_frame(rg_packet)
    
    print("\n--- Podsumowanie odebranych wiadomości ---")
    for topic, msg in node.published_messages:
        print(f"Topic: {topic}")
        if isinstance(msg, Twist):
            print(f"  linear:  x={msg.linear.x:.2f}, y={msg.linear.y:.2f}, z={msg.linear.z:.2f}")
            print(f"  angular: z={msg.angular.z:.2f}")
        elif isinstance(msg, Float32MultiArray):
            print(f"  data: {list(msg.data)}")
            
    rclpy.shutdown()

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Quick test script to publish mock joint states to ROS2
Use this if you don't have a real robot but want to test WebSocket streaming
"""

import rclpy
from rclpy.node import Node
 
from sensor_msgs.msg import JointState
import math
import time

class MockJointStatePublisher(Node):
    def __init__(self):
        super().__init__('mock_joint_state_publisher')
        
        self.publisher = self.create_publisher(JointState, '/joint_states', 10)
        self.timer = self.create_timer(0.05, self.publish_joint_states)  # 20 Hz
        
        self.joint_names = [
            'joint_base',
            'joint_shoulder',
            'joint_elbow',
            'joint_wrist_pitch',
            'joint_wrist_roll',
            'joint_gripper'
        ]
        
        self.t = 0.0
        self.get_logger().info('Mock Joint State Publisher started')
        self.get_logger().info(f'Publishing to /joint_states at 20Hz')
        
    def publish_joint_states(self):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = self.joint_names
        
        # Generate smooth sinusoidal motion for demonstration
        self.t += 0.05
        
        msg.position = [
            0.3 * math.sin(self.t * 0.5),           # base - slow rotation
            -0.5 + 0.3 * math.sin(self.t * 0.7),    # shoulder
            1.0 + 0.5 * math.sin(self.t * 0.6),     # elbow
            -0.3 * math.sin(self.t * 0.8),          # wrist pitch
            self.t * 0.2,                            # wrist roll - continuous
            0.04 * (1 + math.sin(self.t)),          # gripper - open/close
        ]
        
        msg.velocity = [0.0] * len(self.joint_names)
        msg.effort = [0.0] * len(self.joint_names)
        
        self.publisher.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    
    node = MockJointStatePublisher()
    
    try:
        print("🤖 Publishing mock joint states...")
        print("   Topic: /joint_states")
        print("   Rate: 20 Hz")
        print("   Ctrl+C to stop")
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

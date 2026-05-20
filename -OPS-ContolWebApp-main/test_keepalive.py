import logging
import rclpy
import rclpy.node
import time
from backend.services.ros_node import ROSNode

logging.basicConfig(level=logging.INFO)

def run_test():
    rclpy.init()
    node = ROSNode()
    
    # Mock a watcher that just received a point
    node.science_watchers["test_topic"] = {
        "topic": "test_topic",
        "pending": False,
        "frequency_hz": 5.0, # 0.2s interval
        "last_store_time": time.time(),
        "buffer": [{"timestamp": "now", "value": 150}],
        "max_points": 50
    }
    
    print("Buffer start length:", len(node.science_watchers["test_topic"]["buffer"]))
    
    # Spin the node a little bit to see if the timer pushes items
    end_time = time.time() + 1.2
    while time.time() < end_time:
        rclpy.spin_once(node, timeout_sec=0.1)
        
    print("Buffer end length:", len(node.science_watchers["test_topic"]["buffer"]))
    print("Last element:", node.science_watchers["test_topic"]["buffer"][-1])
    
    # Expected: ~5 new elements (since 1s passed at 5hz)
    
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    run_test()

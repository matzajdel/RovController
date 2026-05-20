import sys
sys.path.append("/home/ar/Documents/GitHub/-OPS-ContolWebApp/backend")

from unittest.mock import patch
from services.advanced_steering import SteeringNewService, SteeringState, DriveMode

class MockNode:
    call_count = 0
    def publish_twist_full(self, twist):
        self.call_count += 1
        print(f"PUBLISHING TWIST #{self.call_count}: {twist}")

@patch('services.advanced_steering.get_ros_node')
def test(mock_get_ros_node):
    mn = MockNode()
    mock_get_ros_node.return_value = mn
    s = SteeringNewService()
    state = SteeringState(drive_mode=DriveMode.PROSTY, axes={"right_y": 0.0, "right_x": 0.0, "rt": 1.0})
    s._publish_twist(state)
    s._publish_twist(state)
    s._publish_twist(state)
    print("FINISHED. Call count:", mn.call_count)

test()

import sys
sys.path.append("/home/ar/Documents/GitHub/-OPS-ContolWebApp/backend")
from services.advanced_steering import SteeringNewService, SteeringState, DriveMode

print("Testing with rt=0.0 (ROS default until touched)")
s = SteeringNewService()
state = SteeringState(drive_mode=DriveMode.PROSTY, axes={"right_y": 0.0, "right_x": 0.0, "rt": 0.0})
s._publish_twist(state)
print(state.last_twist)

print("Testing with rt=1.0 (Web default until touched)")
state2 = SteeringState(drive_mode=DriveMode.PROSTY, axes={"right_y": 0.0, "right_x": 0.0, "rt": 1.0})
s._publish_twist(state2)
print(state2.last_twist)

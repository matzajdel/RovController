import sys
sys.path.append("/home/ar/Documents/GitHub/-OPS-ContolWebApp/backend")

from services.advanced_steering import SteeringNewService, SteeringState, DriveMode

s = SteeringNewService()
val_vert = 1.0
val_horz = 0.0
val_trigger = -1.0
mode = 0

state = SteeringState(
    drive_mode=DriveMode(mode),
    axes={
        "right_y": -val_vert,
        "right_x": -val_horz,
        "rt": val_trigger
    }
)

linear_z = state.motor_mode  
dir_multiplier = -1.0 if state.reverse_mode else 1.0

right_x = state.axes.get("right_x", 0.0)
right_y = state.axes.get("right_y", 0.0)
val_trigger = state.axes.get("rt", 1.0)
val_vert = -right_y   
val_horz = -right_x   
throttle = (1.0 - val_trigger) / 2.0
if throttle < 0.05:
    throttle = 0.0

abs_vert = abs(val_vert)
abs_horz = abs(val_horz)
deadzone = 0.15 # DEADZONE defined in file
in_vertical = (abs_vert >= abs_horz) and (abs_vert > deadzone)
in_horizontal = (abs_horz > abs_vert) and (abs_horz > deadzone)

linear_x = 0.0
linear_y = 0.0
angular_z = 0.0

print(f"in_vertical={in_vertical} in_horizontal={in_horizontal} throttle={throttle}")

if state.drive_mode == DriveMode.PROSTY:
    if in_vertical or (throttle > 0.0 and not in_horizontal):
        direction = 1.0 if val_vert >= 0 else -1.0
        linear_x = throttle * state.max_speed * direction * dir_multiplier
        linear_y = 0.0
        print(f"PATH 1: lx={linear_x}")
    elif in_horizontal:
        pass
    else:
        pass

twist_tuple = (
    float(f"{linear_x:.3f}"),
    float(f"{linear_y:.3f}"),
    float(f"{linear_z:.3f}"),
    0.0,
    0.0,
    float(f"{angular_z:.3f}"),
)
print("TWIST ROUNDING: ", twist_tuple)

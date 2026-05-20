import math

def calculate_twist_test(val_vert, val_horz, val_trigger, mode, max_speed=1.0, max_turn=1.0, reverse_mode=False):
    dir_multiplier = -1.0 if reverse_mode else 1.0

    throttle = (1.0 - val_trigger) / 2.0
    if throttle < 0.05: throttle = 0.0

    abs_vert = abs(val_vert)
    abs_horz = abs(val_horz)
    deadzone = 0.15
    in_vertical = (abs_vert >= abs_horz) and (abs_vert > deadzone)
    in_horizontal = (abs_horz > abs_vert) and (abs_horz > deadzone)

    linear_x = 0.0
    linear_y = 0.0
    angular_z = 0.0

    if mode == 0:  # PROSTY
        if in_vertical or (throttle > 0.0 and not in_horizontal):
            direction = 1.0 if val_vert >= 0 else -1.0
            linear_x = throttle * max_speed * direction * dir_multiplier
            linear_y = 0.0
        elif in_horizontal:
            linear_x = 0.0
            linear_y = (throttle * max_speed) * dir_multiplier * (-1.0 if val_horz >= 0 else 1.0) + (-0.05 if val_horz >= 0 else 0.05)
        else:
            linear_x = 0.0
            linear_y = 0.0
        angular_z = 0.0

    elif mode == 1:  # SKRET
        skret_gain = 0.05
        if abs_vert > 0.1:
            linear_x = (val_vert * max_speed * skret_gain) * dir_multiplier * (throttle * 20 if throttle > 0.0 else 1)
        else:
            linear_x = 0.0

        if abs_horz > 0.1:
            linear_y = (-val_horz * max_speed * skret_gain) * dir_multiplier * (throttle * 20 if throttle > 0.0 else 1)
        else:
            linear_y = 0.0
        angular_z = 0.0

    elif mode == 2:  # OBROT
        linear_x = 0.0
        linear_y = 0.0
        if abs_horz > deadzone:
            angular_z = (val_horz * max_turn) * throttle * dir_multiplier + (-0.05 if val_horz >= 0 else 0.05)
        else:
            angular_z = 0.0

    elif mode == 3:  # FREESTYLE
        linear_x = val_vert * max_speed
        linear_y = 0.0
        p = 3
        angular_z = math.copysign(abs(val_horz) ** p, val_horz) * max_turn

    return {"linear_x": linear_x, "linear_y": linear_y, "angular_z": angular_z}

# test values
inputs = [
    # neutral
    (0.0, 0.0, 1.0),
    # gas pushed, no stick
    (0.0, 0.0, -1.0),
    # gas push, stick up
    (1.0, 0.0, -1.0),
    # gas push, stick down
    (-1.0, 0.0, -1.0),
    # gas push, stick right
    (0.0, -1.0, -1.0),
    # gas push, stick left
    (0.0, 1.0, -1.0),
    # gas push, diagonal TR
    (1.0, -1.0, -1.0)
]

for mode in [0, 1, 2, 3]:
    print(f"\nMODE {mode}:")
    for val_vert, val_horz, val_trigger in inputs:
        res = calculate_twist_test(val_vert, val_horz, val_trigger, mode)
        print(f"V={val_vert:4.1f} H={val_horz:4.1f} T={val_trigger:4.1f} -> X={res['linear_x']:5.2f} Y={res['linear_y']:5.2f} Z={res['angular_z']:5.2f}")

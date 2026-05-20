import 'dart:async';
import 'dart:math' as math;
import 'models.dart';
import 'rover_client.dart';

enum DriveMode {
  prosty(0),
  skret(1),
  obrot(2),
  freestyle(3);

  final int value;
  const DriveMode(this.value);

  factory DriveMode.fromValue(int val) {
    return DriveMode.values.firstWhere((e) => e.value == val, orElse: () => DriveMode.prosty);
  }
}

class ControlService {
  final RoverClient roverClient;

  // Steering parameters
  DriveMode driveMode = DriveMode.prosty;
  bool reverseMode = false;
  double motorMode = 1.0; // 0.0 = PID, 1.0 = PWM
  double maxSpeed = 1.0;
  double maxTurn = 1.0;
  String targetTopic = "cmd_vel";

  // Controller axes and buttons
  final Map<String, double> axes = {
    "left_x": 0.0,
    "left_y": 0.0,
    "right_x": 0.0,
    "right_y": 0.0,
    "lt": 1.0,
    "rt": 1.0,
  };
  final Map<String, int> buttons = {};

  // Manipulator array state (Float64MultiArray of length 6)
  final List<double> arrayState = List.filled(6, 0.0);

  // Simple joystick mode
  bool isJoystickActive = false;
  double joystickX = 0.0;
  double joystickY = 0.0;

  // Continuous publisher loop timer
  Timer? _publisherTimer;
  
  // Track status updates for telemetry
  Map<String, dynamic> lastCommandMap = {};
  String lastUpdateTime = "";

  ControlService({required this.roverClient}) {
    lastUpdateTime = DateTime.now().toIso8601String();
  }

  /// Starts the continuous 10Hz publish loop.
  void start() {
    _publisherTimer?.cancel();
    _publisherTimer = Timer.periodic(const Duration(milliseconds: 100), (_) {
      _publishLoopCallback();
    });
    print("ControlService: Continuous 10Hz publisher started.");
  }

  /// Stops the continuous publish loop and sends a STOP command.
  void stop() {
    _publisherTimer?.cancel();
    _publisherTimer = null;
    publishStop();
    print("ControlService: Continuous publisher stopped.");
  }

  void setDriveMode(int modeId) {
    driveMode = DriveMode.fromValue(modeId);
    print("ControlService: Drive mode changed to ${driveMode.name}");
  }

  void setMotorMode(double mode) {
    motorMode = mode;
    print("ControlService: Motor mode changed to ${mode == 1.0 ? 'PWM' : 'PID'} ($mode)");
  }

  void setSpeedLimits(double speedLimit, double turnLimit) {
    maxSpeed = speedLimit;
    maxTurn = turnLimit;
    print("ControlService: Speed limits set to maxSpeed=$maxSpeed, maxTurn=$maxTurn");
  }

  void setTargetTopic(String topic) {
    targetTopic = topic;
    print("ControlService: Velocity command target topic set to: $topic");
  }

  // --- Input Handlers ---

  void updateJoystickInput(double x, double y) {
    isJoystickActive = true;
    joystickX = x;
    joystickY = y;
  }

  void releaseJoystickInput() {
    isJoystickActive = false;
    joystickX = 0.0;
    joystickY = 0.0;
    publishStop();
  }

  void setArrayTopic(int buttonId, double value) {
    final idx = buttonId - 1;
    if (idx >= 0 && idx < 6) {
      arrayState[idx] = value;
      final msg = {
        "layout": {"dim": [], "data_offset": 0},
        "data": arrayState.toList(),
      };
      roverClient.publish("/array_topic", "std_msgs/msg/Float64MultiArray", msg);
      print("ControlService: Published array state: $arrayState");
    }
  }

  void handleHidMove(String code, double? value, Map<String, double>? axesMap) {
    isJoystickActive = false; // Gamepad event deactivates simple joystick
    if (code == "LJoy" && axesMap != null) {
      axes["left_x"] = double.parse((axesMap["x"] ?? 0.0).toDouble().toStringAsFixed(4));
      axes["left_y"] = double.parse((axesMap["y"] ?? 0.0).toDouble().toStringAsFixed(4));
    } else if (code == "RJoy" && axesMap != null) {
      axes["right_x"] = double.parse((axesMap["x"] ?? 0.0).toDouble().toStringAsFixed(4));
      axes["right_y"] = double.parse((axesMap["y"] ?? 0.0).toDouble().toStringAsFixed(4));
    } else if ((code == "LT" || code == "RT") && value != null) {
      final axisKey = code.toLowerCase();
      // Convert browser 0..1 (released..pressed) to ROS convention 1..-1
      axes[axisKey] = double.parse((1.0 - (value * 2.0)).toStringAsFixed(4));
    }
  }

  void handleHidButton(String code, String action, double? value) {
    isJoystickActive = false;
    final pressed = action == "press" ? 1 : 0;
    buttons[code] = pressed;

    if ((code == "LT" || code == "RT") && value != null) {
      final axisKey = code.toLowerCase();
      axes[axisKey] = double.parse((1.0 - (value * 2.0)).toStringAsFixed(4));
    }

    if (code == "RB") {
      if (driveMode == DriveMode.prosty || driveMode == DriveMode.skret) {
        reverseMode = pressed == 1;
      }
    }
  }

  void handleHidState(List<String> pressedCodes) {
    isJoystickActive = false;
    final codesSet = pressedCodes.toSet();
    final observed = {...buttons.keys, "A", "B", "X", "Y", "RB", "LB"};
    for (final code in observed) {
      buttons[code] = codesSet.contains(code) ? 1 : 0;
    }
    // Update RB reverse mode status
    if (driveMode == DriveMode.prosty || driveMode == DriveMode.skret) {
      reverseMode = buttons["RB"] == 1;
    }
  }

  // --- Publish Actions ---

  void publishStop() {
    final stopTwist = Twist(
      linearX: 0.0,
      linearY: 0.0,
      linearZ: motorMode, // Motor mode is sent in linear.z
      angularX: 0.0,
      angularY: 0.0,
      angularZ: 0.0,
    );
    _sendTwist(stopTwist);
    lastCommandMap = {
      "type": "stop",
      "linear_x": 0.0,
      "angular_z": 0.0,
    };
    lastUpdateTime = DateTime.now().toIso8601String();
  }

  void _publishLoopCallback() {
    if (!roverClient.isConnected) return;

    if (isJoystickActive) {
      // Direct joystick control mapping
      final linearX = joystickY * maxSpeed;
      final angularZ = -joystickX * maxTurn;
      final twist = Twist(
        linearX: double.parse(linearX.toStringAsFixed(3)),
        linearY: 0.0,
        linearZ: motorMode,
        angularX: 0.0,
        angularY: 0.0,
        angularZ: double.parse(angularZ.toStringAsFixed(3)),
      );
      _sendTwist(twist);
      lastCommandMap = {
        "type": "joystick_to_cmd_vel_nav",
        "joystick_x": joystickX,
        "joystick_y": joystickY,
        "linear_x": linearX,
        "angular_z": angularZ,
      };
      lastUpdateTime = DateTime.now().toIso8601String();
    } else {
      // Gamepad control mapping (4 drive modes)
      final safetyStop = buttons.entries.any((e) => e.value == 1 && (e.key.startsWith("BTN_") || e.key.contains("Happy")));
      if (safetyStop) {
        publishStop();
        return;
      }

      final dirMultiplier = reverseMode ? -1.0 : 1.0;
      final rightX = _applyDeadzone(axes["right_x"] ?? 0.0);
      final rightY = _applyDeadzone(axes["right_y"] ?? 0.0);

      final valTrigger = axes["rt"] ?? 1.0;
      final valVert = -rightY; // Invert Y
      final valHorz = rightX;

      // Throttle calculation
      double throttle = (1.0 - valTrigger) / 2.0;
      if (throttle < 0.05) throttle = 0.0;

      final absVert = valVert.abs();
      final absHorz = valHorz.abs();
      const deadzoneVal = 0.15;

      final inVertical = (absVert >= absHorz) && (absVert > deadzoneVal);
      final inHorizontal = (absHorz > absVert) && (absHorz > deadzoneVal);

      double linearX = 0.0;
      double linearY = 0.0;
      double angularZ = 0.0;

      switch (driveMode) {
        case DriveMode.prosty:
          if (inVertical || (throttle > 0.0 && !inHorizontal)) {
            final direction = valVert >= 0 ? 1.0 : -1.0;
            linearX = throttle * maxSpeed * dirMultiplier * direction;
            linearY = 0.0;
          } else if (inHorizontal) {
            linearX = 0.0;
            linearY = (throttle * maxSpeed) * dirMultiplier * (valHorz >= 0 ? -1.0 : 1.0) + (valHorz >= 0 ? -0.05 : 0.05);
          }
          break;

        case DriveMode.skret:
          const skretGain = 0.005;
          if (absVert > 0.1) {
            linearX = (valVert * maxSpeed * skretGain) * dirMultiplier * (throttle > 0.0 ? throttle * 20.0 : 1.0);
          }
          if (absHorz > 0.1) {
            linearY = (-valHorz * maxSpeed * skretGain) * dirMultiplier * (throttle > 0.0 ? throttle * 20.0 : 1.0);
          }
          break;

        case DriveMode.obrot:
          if (absHorz > deadzoneVal) {
            angularZ = (valHorz * maxTurn) * throttle * dirMultiplier + (valHorz >= 0 ? -0.05 : 0.05);
          }
          break;

        case DriveMode.freestyle:
          linearX = valVert * maxSpeed;
          angularZ = (valHorz == 0 ? 0.0 : valHorz.sign * math.pow(valHorz.abs(), 3.0)) * maxTurn;
          break;
      }

      final twist = Twist(
        linearX: double.parse(linearX.toStringAsFixed(3)),
        linearY: double.parse(linearY.toStringAsFixed(3)),
        linearZ: motorMode,
        angularX: 0.0,
        angularY: 0.0,
        angularZ: double.parse(angularZ.toStringAsFixed(3)),
      );

      _sendTwist(twist);
      lastCommandMap = {
        "type": "gamepad_to_cmd_vel",
        "drive_mode": driveMode.name,
        "reverse_mode": reverseMode,
        "linear_x": twist.linearX,
        "linear_y": twist.linearY,
        "angular_z": twist.angularZ,
      };
      lastUpdateTime = DateTime.now().toIso8601String();
    }
  }

  void _sendTwist(Twist twist) {
    final msg = {
      "linear": {
        "x": twist.linearX,
        "y": twist.linearY,
        "z": twist.linearZ,
      },
      "angular": {
        "x": twist.angularX,
        "y": twist.angularY,
        "z": twist.angularZ,
      }
    };
    roverClient.publish(targetTopic, "geometry_msgs/msg/Twist", msg);
  }

  double _applyDeadzone(double value) {
    const deadzoneVal = 0.15;
    if (value.abs() < deadzoneVal) return 0.0;
    return value;
  }

  RobotStatus getStatus() {
    return RobotStatus(
      connected: roverClient.isConnected,
      lastCommand: lastCommandMap.isNotEmpty ? lastCommandMap : null,
      lastUpdate: lastUpdateTime,
    );
  }
}

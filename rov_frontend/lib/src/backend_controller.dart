import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:rov_backend/rov_backend.dart';

class BackendController extends ChangeNotifier {
  final RovBackend backend = RovBackend();

  StreamSubscription<bool>? _connectionSub;
  bool _backendStarted = false;
  bool _connected = false;

  bool get backendStarted => _backendStarted;
  bool get connected => _connected;

  /// Default rover IP used when the UI does not provide one.
  /// Keep this in sync with project conventions.
  static const String defaultRoverIp = '192.168.2.100';

  Future<void> connect({String roverIp = defaultRoverIp}) async {
    // The rov_backend package uses dart:io (HttpServer, File, WebSocket) which
    // is not available on web. Skip the native backend on web — the app runs
    // in UI-only / demo mode.
    if (kIsWeb) {
      print('BackendController: Web platform — skipping native backend start.');
      return;
    }

    if (!_backendStarted) {
      final dir = await getApplicationDocumentsDirectory();
      await backend.start(
        roverIp: roverIp,
        storagePath: dir.path,
      );
      _backendStarted = true;

      _connectionSub?.cancel();
      _connectionSub = backend.roverClient.connectionStatusStream.listen((val) {
        _connected = val;
        notifyListeners();
      });

      _connected = backend.roverClient.isConnected;
      notifyListeners();
      return;
    }

    backend.roverClient.connect();
  }

  void disconnect() {
    if (!_backendStarted) return;

    // Safety stop before disconnect.
    try {
      backend.controlService.publishStop();
    } catch (_) {}

    backend.roverClient.disconnect();
  }

  void emergencyStop() {
    if (!_backendStarted) return;
    backend.controlService.publishStop();
  }

  void setJoystick(double x, double y) {
    if (!_backendStarted) return;
    backend.controlService.updateJoystickInput(x, y);
  }

  void releaseJoystick() {
    if (!_backendStarted) return;
    backend.controlService.releaseJoystickInput();
  }

  /// Publishes a power circuit command to the rover's /string_topic.
  ///
  /// The [message] should follow the format "CX-ON" or "CX-OFF"
  /// (e.g. "C1-ON", "C3-OFF"), matching the ROS node in power_kurwa_working.py.
  void publishPowerCircuit(String message) {
    if (kIsWeb || !_backendStarted) return;
    backend.roverClient.publishRaw(
      '/string_topic',
      'std_msgs/msg/String',
      message,
    );
  }

  /// Publishes manipulator joint values to /array_topic as Float64MultiArray.
  ///
  /// [values] must be a 6-element list representing axes 1–6.
  /// Values are in the range −100..100 (matching gamepad_ros2_bridge.py convention).
  /// Internally calls ControlService.publishManipulatorValues which sends
  /// the full Float64MultiArray to /array_topic.
  void publishManipulatorArray(List<double> values) {
    if (kIsWeb || !_backendStarted) return;
    backend.controlService.publishManipulatorValues(values);
  }

  @override
  void dispose() {
    _connectionSub?.cancel();
    // Best-effort shutdown.
    backend.stop();
    super.dispose();
  }
}

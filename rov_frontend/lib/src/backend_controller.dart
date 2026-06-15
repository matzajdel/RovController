<<<<<<< HEAD
import 'dart:async';

import 'package:flutter/foundation.dart';

import 'services/rov_api_client.dart';

/// Controls the connection to the rover's Python backend (port 2137).
///
/// Architecture:
///   Flutter → RovApiClient → ws://ip:2137/ws  (joystick, ping)
///                          → http://ip:2137/  (stop, manipulator)
///
/// No Docker, no ROSBridge needed. Just run `./start_service.sh` on the Geekom.
class BackendController extends ChangeNotifier {
  RovApiClient? _client;
  StreamSubscription<bool>? _connectionSub;

  bool _connected = false;
  String? _lastError;

  bool get connected => _connected;
  bool get backendStarted => _client != null;
  String? get lastError => _lastError;

  /// Default Geekom backend IP.
  static const String defaultRoverIp = '192.168.2.50';

  /// Python FastAPI backend port (set via env PORT or default 2137).
  static const int defaultBackendPort = 2137;

  // ---------------------------------------------------------------------------
  // Connection
  // ---------------------------------------------------------------------------

  Future<void> connect({
    String roverIp = defaultRoverIp,
    int port = defaultBackendPort,
  }) async {
    if (kIsWeb) return; // web: no native sockets

    _lastError = null;

    // Same IP already active — just re-trigger connect
    if (_client != null && _client!.ip == roverIp && _client!.port == port) {
      _client!.connect();
      return;
    }

    // Different IP/port — tear down old client
    _connectionSub?.cancel();
    _connectionSub = null;
    _client?.disconnect();
    _client = null;
    _connected = false;
    notifyListeners();

    // Small pause to let OS release the previous socket cleanly
    await Future.delayed(const Duration(milliseconds: 200));

    _client = RovApiClient(ip: roverIp, port: port);

    _connectionSub = _client!.connectionStatusStream.listen((val) {
      _connected = val;
      _lastError = val
          ? null
          : 'Nie można połączyć z backendem\n'
              'ws://$roverIp:$port/ws\n'
              'Sprawdź czy łazik jest włączony i start_service.sh działa.';
      notifyListeners();
    });

    _client!.connect();
    notifyListeners();
  }

  void disconnect() {
    _client?.releaseJoystick();
    _client?.disconnect();
    _connected = false;
    _lastError = null;
    notifyListeners();
  }

  // ---------------------------------------------------------------------------
  // Control commands
  // ---------------------------------------------------------------------------

  void emergencyStop() {
    _client?.publishStop();
  }

  void setJoystick(double x, double y) {
    _client?.updateJoystick(x, y);
  }

  void releaseJoystick() {
    _client?.releaseJoystick();
  }

  /// Publishes manipulator joint values to /array_topic as Float64MultiArray.
  /// [values] — 6-element list (axes 1–6), range −100..100.
  void publishManipulatorArray(List<double> values) {
    _client?.publishManipulatorArray(values);
  }

  /// Publishes a power circuit command (CX-ON / CX-OFF) to /string_topic.
  /// NOTE: Not yet implemented for Python backend.
  void publishPowerCircuit(String message) {
    // TODO: Add /custom_topic String support or dedicated endpoint.
    debugPrint('publishPowerCircuit not yet implemented: $message');
  }

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  @override
  void dispose() {
    _connectionSub?.cancel();
    _client?.dispose();
    super.dispose();
  }
}
=======
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:rov_backend/rov_backend.dart';

class CommandLogEntry {
  final String key;
  final DateTime timestamp;
  final String title;
  final String details;

  const CommandLogEntry({
    required this.key,
    required this.timestamp,
    required this.title,
    required this.details,
  });

  CommandLogEntry copyWith({
    String? key,
    DateTime? timestamp,
    String? title,
    String? details,
  }) {
    return CommandLogEntry(
      key: key ?? this.key,
      timestamp: timestamp ?? this.timestamp,
      title: title ?? this.title,
      details: details ?? this.details,
    );
  }
}

class BackendController extends ChangeNotifier {
  final RovBackend backend = RovBackend();

  StreamSubscription<bool>? _connectionSub;
  bool _backendStarted = false;
  bool _connected = false;
  bool _demoMode = false;
  final List<CommandLogEntry> _commandHistory = [];

  bool get backendStarted => _backendStarted;
  bool get connected => _connected;
  bool get demoMode => _demoMode;
  bool get controlEnabled => _demoMode || _connected;
  List<CommandLogEntry> get commandHistory =>
      List.unmodifiable(_commandHistory);

  /// Default rover IP used when the UI does not provide one.
  /// Keep this in sync with project conventions.
  static const String defaultRoverIp = '192.168.2.100';

  void setDemoMode(bool enabled) {
    if (_demoMode == enabled) return;

    _demoMode = enabled;
    notifyListeners();
  }

  void toggleDemoMode() {
    setDemoMode(!_demoMode);
  }

  void clearCommandHistory() {
    if (_commandHistory.isEmpty) return;

    _commandHistory.clear();
    notifyListeners();
  }

  void _recordCommand(String key, String title, String details) {
    _commandHistory.insert(
      0,
      CommandLogEntry(
        key: key,
        timestamp: DateTime.now(),
        title: title,
        details: details,
      ),
    );

    if (_commandHistory.length > 24) {
      _commandHistory.removeLast();
    }

    notifyListeners();
  }

  void _upsertCommand(String key, String title, String details) {
    final existingIndex = _commandHistory.indexWhere((entry) => entry.key == key);
    if (existingIndex >= 0) {
      final updatedEntry = _commandHistory[existingIndex].copyWith(
        timestamp: DateTime.now(),
        title: title,
        details: details,
      );
      _commandHistory.removeAt(existingIndex);
      _commandHistory.insert(0, updatedEntry);
    } else {
      _commandHistory.insert(
        0,
        CommandLogEntry(
          key: key,
          timestamp: DateTime.now(),
          title: title,
          details: details,
        ),
      );
    }

    if (_commandHistory.length > 24) {
      _commandHistory.removeLast();
    }

    notifyListeners();
  }

  String _twistCommandDetails(double x, double y) {
    final linearX = y.toStringAsFixed(2);
    final angularZ = (-x).toStringAsFixed(2);

    return '/cmd_vel → geometry_msgs/msg/Twist { '
        'linear: { x: $linearX, y: 0.00, z: 1.00 }, '
        'angular: { x: 0.00, y: 0.00, z: $angularZ } }';
  }

  Future<void> connect({String roverIp = defaultRoverIp}) async {
    // The rov_backend package uses dart:io (HttpServer, File, WebSocket) which
    // is not available on web. Skip the native backend on web — the app runs
    // in UI-only / demo mode.
    if (kIsWeb) {
      debugPrint('BackendController: Web platform — skipping native backend start.');
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
    if (!_backendStarted && !_demoMode) return;

    _upsertCommand(
      'cmd_vel',
      'Joystick',
      '/cmd_vel → geometry_msgs/msg/Twist { '
          'linear: { x: 0.00, y: 0.00, z: 1.00 }, '
          'angular: { x: 0.00, y: 0.00, z: 0.00 } }',
    );

    if (_demoMode) return;

    backend.controlService.publishStop();
  }

  void setJoystick(double x, double y) {
    if (!_backendStarted && !_demoMode) return;

    _upsertCommand('cmd_vel', 'Joystick', _twistCommandDetails(x, y));

    if (_demoMode) return;

    backend.controlService.updateJoystickInput(x, y);
  }

  void releaseJoystick() {
    if (!_backendStarted && !_demoMode) return;

    _upsertCommand(
      'cmd_vel',
      'Joystick',
      '/cmd_vel → geometry_msgs/msg/Twist { '
          'linear: { x: 0.00, y: 0.00, z: 1.00 }, '
          'angular: { x: 0.00, y: 0.00, z: 0.00 } }',
    );

    if (_demoMode) return;

    backend.controlService.releaseJoystickInput();
  }

  /// Publishes a power circuit command to the rover's /string_topic.
  ///
  /// The [message] should follow the format "CX-ON" or "CX-OFF"
  /// (e.g. "C1-ON", "C3-OFF"), matching the ROS node in power_kurwa_working.py.
  void publishPowerCircuit(String message) {
    if (!demoMode && (kIsWeb || !_backendStarted)) return;

    _recordCommand(
      'powerbox',
      'powerbox',
      '/string_topic → std_msgs/msg/String { data: "$message" }',
    );

    if (_demoMode) return;

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
    if (!demoMode && (kIsWeb || !_backendStarted)) return;

    final formattedValues = values
        .map((value) => value.toStringAsFixed(1))
        .join(', ');
    _recordCommand(
      'manipulator',
      'manipulator',
      '/array_topic → std_msgs/msg/Float64MultiArray { data: [$formattedValues] }',
    );

    if (_demoMode) return;

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
>>>>>>> 7e38cc9bd92fd790881323230b05c07ff2994f24

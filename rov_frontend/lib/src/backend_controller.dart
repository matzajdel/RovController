
import 'dart:async';

import 'package:flutter/foundation.dart';

import 'services/rov_api_client.dart';

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
  bool _demoMode = false;
  final List<CommandLogEntry> _commandHistory = [];

  bool get connected => _connected;
  bool get backendStarted => _client != null;
  String? get lastError => _lastError;
  bool get demoMode => _demoMode;
  bool get controlEnabled => _demoMode || _connected;
  List<CommandLogEntry> get commandHistory => List.unmodifiable(_commandHistory);

  /// Default Geekom backend IP.
  static const String defaultRoverIp = '192.168.2.50';

  /// Python FastAPI backend port (set via env PORT or default 2137).
  static const int defaultBackendPort = 2137;

  void setDemoMode(bool enabled) {
    if (_demoMode == enabled) return;

    _demoMode = enabled;
    notifyListeners();
  }

  void toggleDemoMode() => setDemoMode(!_demoMode);

  void clearCommandHistory() {
    if (_commandHistory.isEmpty) return;

    _commandHistory.clear();
    notifyListeners();
  }

  void _upsertCommand(String key, String title, String details) {
    final index = _commandHistory.indexWhere((entry) => entry.key == key);
    final now = DateTime.now();

    if (index >= 0) {
      final updated = _commandHistory[index].copyWith(
        timestamp: now,
        title: title,
        details: details,
      );
      _commandHistory.removeAt(index);
      _commandHistory.insert(0, updated);
    } else {
      _commandHistory.insert(
        0,
        CommandLogEntry(
          key: key,
          timestamp: now,
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

  String _twistDetails(double x, double y) {
    final linearX = y.toStringAsFixed(2);
    final angularZ = (-x).toStringAsFixed(2);

    return '/cmd_vel → geometry_msgs/msg/Twist { '
        'linear: { x: $linearX, y: 0.00, z: 1.00 }, '
        'angular: { x: 0.00, y: 0.00, z: $angularZ } }';
  }

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
    if (!_demoMode && !_connected) return;

    _upsertCommand(
      'cmd_vel',
      'Joystick',
      '/cmd_vel → geometry_msgs/msg/Twist { '
          'linear: { x: 0.00, y: 0.00, z: 1.00 }, '
          'angular: { x: 0.00, y: 0.00, z: 0.00 } }',
    );

    if (_demoMode) return;

    _client?.publishStop();
  }

  void setJoystick(double x, double y) {
    if (!_demoMode && !_connected) return;

    _upsertCommand('cmd_vel', 'Joystick', _twistDetails(x, y));

    if (_demoMode) return;

    _client?.updateJoystick(x, y);
  }

  void releaseJoystick() {
    if (!_demoMode && !_connected) return;

    _upsertCommand(
      'cmd_vel',
      'Joystick',
      '/cmd_vel → geometry_msgs/msg/Twist { '
          'linear: { x: 0.00, y: 0.00, z: 1.00 }, '
          'angular: { x: 0.00, y: 0.00, z: 0.00 } }',
    );

    if (_demoMode) return;

    _client?.releaseJoystick();
  }

  /// Publishes manipulator joint values to /array_topic as Float64MultiArray.
  /// [values] — 6-element list (axes 1–6), range −100..100.
  void publishManipulatorArray(List<double> values) {
    if (!_demoMode && !_connected) return;

    final formattedValues = values.map((value) => value.toStringAsFixed(1)).join(', ');
    _upsertCommand(
      'manipulator',
      'Manipulator',
      '/array_topic → std_msgs/msg/Float64MultiArray { data: [$formattedValues] }',
    );

    if (_demoMode) return;

    _client?.publishManipulatorArray(values);
  }

  /// Publishes a power circuit command (CX-ON / CX-OFF) to /string_topic.
  /// NOTE: Not yet implemented for Python backend.
  void publishPowerCircuit(String message) {
    if (!_demoMode && !_connected) return;

    _upsertCommand(
      'powerbox',
      'Powerbox',
      '/string_topic → std_msgs/msg/String { data: "$message" }',
    );

    if (_demoMode) return;

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

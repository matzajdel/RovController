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

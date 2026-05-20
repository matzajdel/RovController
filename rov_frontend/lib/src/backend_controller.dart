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

  @override
  void dispose() {
    _connectionSub?.cancel();
    // Best-effort shutdown.
    backend.stop();
    super.dispose();
  }
}

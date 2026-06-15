import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// HTTP + WebSocket client that talks directly to the Python FastAPI backend
/// at ws://ip:port/ws (port 2137 by default).
///
/// This replaces the ROSBridge approach (port 9090) — no Docker required.
/// The Python backend runs `./start_service.sh` and exposes:
///   • WebSocket /ws   — real-time joystick control
///   • POST /stop      — emergency stop
///   • POST /custom_topic — generic ROS2 topic publisher
///
/// WebSocket message format (sent to Python backend):
///   {"type": "joystick",         "x": <float>, "y": <float>}
///   {"type": "joystick_release"}
///   {"type": "ping"}
class RovApiClient {
  final String ip;
  final int port;

  static const _wsPath = '/ws';
  // 10Hz republish interval — keeps rover moving even if events slow down
  static const _joystickHz = Duration(milliseconds: 100);

  WebSocket? _ws;
  bool _isConnected = false;
  bool _shouldReconnect = true;

  Timer? _reconnectTimer;
  Timer? _pingTimer;
  Timer? _joystickTimer;

  double _lastJoyX = 0.0;
  double _lastJoyY = 0.0;
  bool _joystickActive = false;

  final StreamController<bool> _connectionStatusController =
      StreamController<bool>.broadcast();

  Stream<bool> get connectionStatusStream => _connectionStatusController.stream;
  bool get isConnected => _isConnected;
  String get wsUrl => 'ws://$ip:$port$_wsPath';
  String get baseUrl => 'http://$ip:$port';

  RovApiClient({required this.ip, this.port = 2137});

  // ---------------------------------------------------------------------------
  // Connection management
  // ---------------------------------------------------------------------------

  void connect() {
    _shouldReconnect = true;
    _attemptConnect();
  }

  Future<void> _attemptConnect() async {
    try {
      _ws = await WebSocket.connect(wsUrl)
          .timeout(const Duration(seconds: 4));

      _isConnected = true;
      _connectionStatusController.add(true);

      // Keepalive ping every 5 s
      _pingTimer?.cancel();
      _pingTimer = Timer.periodic(const Duration(seconds: 5), (_) {
        _sendWs({'type': 'ping'});
      });

      _ws!.listen(
        (_) {/* pong / status messages — ignore for now */},
        onDone: _handleDisconnection,
        onError: (_) => _handleDisconnection(),
        cancelOnError: true,
      );
    } catch (e) {
      debugPrint('RovApiClient connection error: $e');
      _handleDisconnection();
    }
  }

  void _handleDisconnection() {
    _pingTimer?.cancel();
    _stopJoystickTimer();
    _joystickActive = false;
    _isConnected = false;
    _ws = null;
    
    // Always emit false so UI knows connection failed (even on first attempt)
    _connectionStatusController.add(false);

    if (_shouldReconnect) {
      _reconnectTimer?.cancel();
      _reconnectTimer =
          Timer(const Duration(seconds: 3), _attemptConnect);
    }
  }

  void disconnect() {
    _shouldReconnect = false;
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    _stopJoystickTimer();
    final wasConnected = _isConnected;
    _isConnected = false;
    _ws?.close();
    _ws = null;
    if (wasConnected) _connectionStatusController.add(false);
  }

  void dispose() {
    disconnect();
    _connectionStatusController.close();
  }

  // ---------------------------------------------------------------------------
  // Joystick
  // ---------------------------------------------------------------------------

  /// Send joystick position to the Python backend.
  /// A 10Hz periodic timer ensures the rover keeps receiving commands
  /// while the stick is held (important if the rover has a cmd_vel watchdog).
  void updateJoystick(double x, double y) {
    _lastJoyX = x;
    _lastJoyY = y;
    _joystickActive = true;
    _sendWs({'type': 'joystick', 'x': x, 'y': y});

    // Start 10Hz republish if not already running
    _joystickTimer ??= Timer.periodic(_joystickHz, (_) {
      if (_joystickActive && _isConnected) {
        _sendWs({'type': 'joystick', 'x': _lastJoyX, 'y': _lastJoyY});
      }
    });
  }

  void releaseJoystick() {
    _joystickActive = false;
    _stopJoystickTimer();
    _lastJoyX = 0.0;
    _lastJoyY = 0.0;
    _sendWs({'type': 'joystick_release'});
  }

  void _stopJoystickTimer() {
    _joystickTimer?.cancel();
    _joystickTimer = null;
  }

  // ---------------------------------------------------------------------------
  // Commands sent via HTTP (for reliability — fire-and-forget)
  // ---------------------------------------------------------------------------

  /// Emergency stop — calls POST /stop on the Python backend.
  void publishStop() {
    releaseJoystick();
    _httpPost('/stop', {}).ignore();
  }

  /// Publish a Float64MultiArray to /array_topic (manipulator).
  /// [values] must be a list of 6 doubles (axes 1–6).
  void publishManipulatorArray(List<double> values) {
    _httpPost('/custom_topic', {
      'topic': '/array_topic',
      'data': values,
      'msg_type': 'Float64MultiArray',
    }).ignore();
  }

  // ---------------------------------------------------------------------------
  // WebSocket helpers
  // ---------------------------------------------------------------------------

  void _sendWs(Map<String, dynamic> message) {
    try {
      if (_ws != null && _isConnected) {
        _ws!.add(json.encode(message));
      }
    } catch (_) {
      // Connection probably dropped — listener will handle reconnect
    }
  }

  // ---------------------------------------------------------------------------
  // HTTP helpers
  // ---------------------------------------------------------------------------

  Future<void> _httpPost(String path, Map<String, dynamic> body) async {
    final client = HttpClient();
    try {
      final req = await client
          .postUrl(Uri.parse('$baseUrl$path'))
          .timeout(const Duration(seconds: 3));
      req.headers.contentType = ContentType.json;
      req.write(json.encode(body));
      final resp =
          await req.close().timeout(const Duration(seconds: 3));
      await resp.drain<void>(); // consume response to avoid socket leak
    } catch (_) {
      // Silently ignore — rover may be momentarily unreachable
    } finally {
      client.close();
    }
  }
}

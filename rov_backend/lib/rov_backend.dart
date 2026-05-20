import 'dart:async';
import 'src/database.dart';
import 'src/control_service.dart';
import 'src/rover_client.dart';
import 'src/server.dart';

export 'src/models.dart';
export 'src/database.dart' show RovDatabase;
export 'src/control_service.dart' show ControlService, DriveMode;
export 'src/rover_client.dart' show RoverClient;
export 'src/server.dart' show RovServer;

/// The main coordinator class for the RovController backend.
///
/// It orchestrates the initialization and lifecycle of the local database,
/// the ROSBridge WebSocket client connection to the rover, the continuous
/// 10Hz driving loop, and the local HTTP & WebSocket server.
class RovBackend {
  RovDatabase? _database;
  RoverClient? _roverClient;
  ControlService? _controlService;
  RovServer? _server;

  bool _isStarted = false;

  /// Returns whether the backend service is currently running.
  bool get isStarted => _isStarted;

  /// Reference to the active local database instance.
  RovDatabase get database {
    if (_database == null) {
      throw StateError("RovBackend must be started before accessing database.");
    }
    return _database!;
  }

  /// Reference to the active rover WebSocket client.
  RoverClient get roverClient {
    if (_roverClient == null) {
      throw StateError("RovBackend must be started before accessing roverClient.");
    }
    return _roverClient!;
  }

  /// Reference to the active controller/joystick steering logic coordinator.
  ControlService get controlService {
    if (_controlService == null) {
      throw StateError("RovBackend must be started before accessing controlService.");
    }
    return _controlService!;
  }

  /// Reference to the active local HTTP & WebSocket server on port 2137.
  RovServer get server {
    if (_server == null) {
      throw StateError("RovBackend must be started before accessing server.");
    }
    return _server!;
  }

  /// Starts the entire backend stack.
  ///
  /// - [roverIp] specifies the IP address of the rover's ROSBridge WebSocket server.
  /// - [storagePath] is the absolute path to a folder on the device (e.g. app documents directory on Android) where database JSON files will be stored.
  /// - [localPort] is the port number for the local HTTP & WebSocket proxy server (defaults to 2137).
  /// - [roverPort] is the port of the rover's ROSBridge WebSocket (defaults to 9090).
  Future<void> start({
    required String roverIp,
    required String storagePath,
    int localPort = 2137,
    int roverPort = 9090,
  }) async {
    if (_isStarted) {
      print("RovBackend: Already started. Stop it before starting again.");
      return;
    }

    print("RovBackend: Starting native backend stack...");

    try {
      // 1. Initialize local persistent database
      _database = RovDatabase(storagePath: storagePath);
      await _database!.init();
      print("RovBackend: Database initialized at $storagePath");

      // 2. Initialize and connect WebSocket to the rover
      _roverClient = RoverClient(ip: roverIp, port: roverPort);
      _roverClient!.connect();
      print("RovBackend: Rover client connecting to ws://$roverIp:$roverPort");

      // 3. Initialize steering coordinator and start 10Hz watchdog loop
      _controlService = ControlService(roverClient: _roverClient!);
      _controlService!.start();

      // 4. Initialize and bind local HTTP & WS server
      _server = RovServer(
        database: _database!,
        controlService: _controlService!,
        roverClient: _roverClient!,
        port: localPort,
      );
      await _server!.start();

      _isStarted = true;
      print("RovBackend: Native backend stack started successfully.");
    } catch (e) {
      print("RovBackend: Failed to start backend: $e");
      // Clean up whatever managed to start
      await stop();
      rethrow;
    }
  }

  /// Stops all background tasks, releases server ports, and closes active sockets.
  Future<void> stop() async {
    if (!_isStarted &&
        _server == null &&
        _controlService == null &&
        _roverClient == null) {
      return;
    }

    print("RovBackend: Shutting down native backend stack...");

    // 1. Stop local HTTP and WebSocket server
    if (_server != null) {
      await _server!.stop();
      _server = null;
    }

    // 2. Stop steering watchdog loop and timers
    if (_controlService != null) {
      _controlService!.stop();
      _controlService = null;
    }

    // 3. Disconnect from the rover
    if (_roverClient != null) {
      _roverClient!.disconnect();
      _roverClient = null;
    }

    // 4. Reset database reference
    _database = null;

    _isStarted = false;
    print("RovBackend: Native backend stack stopped.");
  }
}

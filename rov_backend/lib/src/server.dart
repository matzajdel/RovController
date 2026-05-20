import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'database.dart';
import 'control_service.dart';
import 'rover_client.dart';
import 'models.dart';

class RovServer {
  final RovDatabase database;
  final ControlService controlService;
  final RoverClient roverClient;
  final int port;

  HttpServer? _httpServer;
  final Set<WebSocket> _wsClients = {};
  bool _isRunning = false;

  RovServer({
    required this.database,
    required this.controlService,
    required this.roverClient,
    this.port = 2137,
  });

  bool get isRunning => _isRunning;

  /// Starts the HTTP and WebSocket server on `0.0.0.0:[port]`.
  Future<void> start() async {
    if (_isRunning) return;

    _httpServer = await HttpServer.bind(InternetAddress.anyIPv4, port);
    _isRunning = true;
    print("RovServer: Local server running on http://0.0.0.0:$port");

    _httpServer!.listen((HttpRequest request) {
      _handleRequest(request);
    }, onError: (err) {
      print("RovServer: Server listener error: $err");
    });

    // Listen to connection status changes and trigger active state broadcasts
    roverClient.connectionStatusStream.listen((connected) {
      _broadcastState();
    });
  }

  /// Stops the server and closes all active WebSocket connections.
  Future<void> stop() async {
    _isRunning = false;
    await _httpServer?.close(force: true);
    _httpServer = null;
    for (final ws in _wsClients) {
      try {
        ws.close();
      } catch (_) {}
    }
    _wsClients.clear();
    print("RovServer: Server stopped.");
  }

  void _handleRequest(HttpRequest request) async {
    // Enable CORS to support cross-origin requests from the browser / webview
    request.response.headers.add('Access-Control-Allow-Origin', '*');
    request.response.headers.add('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
    request.response.headers.add('Access-Control-Allow-Headers', 'Origin, Content-Type, Accept');

    // Preflight requests
    if (request.method == 'OPTIONS') {
      request.response.statusCode = HttpStatus.ok;
      await request.response.close();
      return;
    }

    final path = request.uri.path;

    // WebSocket Upgrade Route
    if (path == '/ws') {
      if (WebSocketTransformer.isUpgradeRequest(request)) {
        try {
          final ws = await WebSocketTransformer.upgrade(request);
          _handleWebSocketConnection(ws);
        } catch (e) {
          print("RovServer: WebSocket upgrade error: $e");
          _sendError(request, HttpStatus.internalServerError, "WebSocket upgrade failed");
        }
      } else {
        _sendError(request, HttpStatus.badRequest, "Expected WebSocket upgrade");
      }
      return;
    }

    // Standard REST HTTP Routes
    try {
      if (request.method == 'GET') {
        switch (path) {
          case '/health':
          case '/status':
            _sendJson(request, {
              "status": "healthy",
              "rover_connected": roverClient.isConnected,
              "rover_ip": roverClient.ip,
            });
            break;

          case '/steering/get_state':
            _sendJson(request, {
              "status": "success",
              "state": {
                "drive_mode": controlService.driveMode.value,
                "drive_mode_name": controlService.driveMode.name.toUpperCase(),
                "motor_mode": controlService.motorMode,
                "max_speed": controlService.maxSpeed,
                "max_turn": controlService.maxTurn,
                "reverse_mode": controlService.reverseMode,
                "target_topic": controlService.targetTopic,
                "array_state": controlService.arrayState,
              }
            });
            break;

          case '/ros/saved_commands':
            final cmds = database.getSavedCommands();
            final Map<String, dynamic> rawCmds = {};
            cmds.forEach((topic, list) {
              rawCmds[topic] = list.map((c) => c.toJson()).toList();
            });
            _sendJson(request, {"commands": rawCmds});
            break;

          case '/ros/ui_config':
            final topic = request.uri.queryParameters['topic'];
            final config = database.getUiConfig(topic: topic);
            _sendJson(request, config);
            break;

          case '/ros/science_layout':
            final instance = request.uri.queryParameters['instance'] ?? 'default';
            final layout = await database.getScienceLayout(instance: instance);
            _sendJson(request, layout);
            break;

          default:
            _sendError(request, HttpStatus.notFound, "Endpoint not found");
        }
      } else if (request.method == 'POST') {
        final body = await _readJsonBody(request);

        // Dynamic manipulator button array router /array_topic/{button_id}
        if (path.startsWith('/array_topic/')) {
          final buttonIdStr = path.substring('/array_topic/'.length);
          final buttonId = int.tryParse(buttonIdStr);
          if (buttonId == null || buttonId < 1 || buttonId > 6) {
            _sendError(request, HttpStatus.badRequest, "Invalid button_id");
            return;
          }
          final rawValue = body['value'];
          if (rawValue == null) {
            _sendError(request, HttpStatus.badRequest, "Missing 'value'");
            return;
          }
          final value = (rawValue as num).toDouble();
          controlService.setArrayTopic(buttonId, value);
          _sendJson(request, {
            "status": "success",
            "button": buttonId,
            "value": value,
            "timestamp": DateTime.now().toIso8601String(),
          });
          return;
        }

        switch (path) {
          case '/joystick':
            final x = (body['x'] ?? 0.0) as num;
            final y = (body['y'] ?? 0.0) as num;
            controlService.updateJoystickInput(x.toDouble(), y.toDouble());
            _sendJson(request, {"status": "success"});
            break;

          case '/joystick/release':
            controlService.releaseJoystickInput();
            _sendJson(request, {"status": "success"});
            break;

          case '/joystick/activate':
            controlService.isJoystickActive = true;
            _sendJson(request, {"status": "success"});
            break;

          case '/joystick/deactivate':
            controlService.isJoystickActive = false;
            controlService.publishStop();
            _sendJson(request, {"status": "success"});
            break;

          case '/cmd_vel':
            final lx = (body['linear_x'] ?? 0.0) as num;
            final az = (body['angular_z'] ?? 0.0) as num;
            final twist = Twist(
              linearX: lx.toDouble(),
              angularZ: az.toDouble(),
              linearZ: controlService.motorMode,
            );
            roverClient.publishRaw(controlService.targetTopic, "geometry_msgs/msg/Twist", twist.toJson());
            _sendJson(request, {"status": "success"});
            break;

          case '/cmd_vel_full':
            final twist = Twist.fromJson(body);
            roverClient.publishRaw(controlService.targetTopic, "geometry_msgs/msg/Twist", twist.toJson());
            _sendJson(request, {"status": "success"});
            break;

          case '/stop':
            controlService.publishStop();
            _sendJson(request, {"status": "success"});
            break;

          case '/steering/set_drive_mode':
            final modeId = body['mode_id'];
            if (modeId == null) {
              _sendError(request, HttpStatus.badRequest, "Missing 'mode_id'");
              return;
            }
            controlService.setDriveMode((modeId as num).toInt());
            _sendJson(request, {
              "status": "success",
              "drive_mode": controlService.driveMode.value,
              "drive_mode_name": controlService.driveMode.name.toUpperCase(),
            });
            break;

          case '/steering/set_motor_mode':
            final motorMode = body['motor_mode'];
            if (motorMode == null) {
              _sendError(request, HttpStatus.badRequest, "Missing 'motor_mode'");
              return;
            }
            controlService.setMotorMode((motorMode as num).toDouble());
            _sendJson(request, {
              "status": "success",
              "motor_mode": controlService.motorMode,
            });
            break;

          case '/steering/set_speed_limits':
            final maxSpeed = body['max_speed'];
            final maxTurn = body['max_turn'];
            if (maxSpeed == null || maxTurn == null) {
              _sendError(request, HttpStatus.badRequest, "Missing limits");
              return;
            }
            controlService.setSpeedLimits((maxSpeed as num).toDouble(), (maxTurn as num).toDouble());
            _sendJson(request, {
              "status": "success",
              "max_speed": controlService.maxSpeed,
              "max_turn": controlService.maxTurn,
            });
            break;

          case '/steering/set_target_topic':
            final topic = body['topic'] as String?;
            if (topic == null || topic.isEmpty) {
              _sendError(request, HttpStatus.badRequest, "Missing 'topic'");
              return;
            }
            controlService.setTargetTopic(topic.trim());
            _sendJson(request, {
              "status": "success",
              "target_topic": controlService.targetTopic,
            });
            break;

          case '/ros/saved_commands':
            final topic = body['topic'] as String?;
            final name = body['name'] as String?;
            final value = body['value'];
            final type = body['type'] as String? ?? 'std_msgs/msg/Float64';
            final isDefault = (body['isDefault'] ?? false) as bool;
            final labels = (body['labels'] as List?)?.map((e) => e.toString()).toList() ?? [];

            if (topic == null || name == null) {
              _sendError(request, HttpStatus.badRequest, "Missing topic or name");
              return;
            }
            await database.saveCommand(
              topic: topic,
              name: name,
              value: value,
              type: type,
              isDefault: isDefault,
              labels: labels,
            );
            _sendJson(request, {"status": "success", "message": "Command '$name' saved"});
            break;

          case '/ros/ui_config':
            final topic = body['topic'] as String?;
            final config = body['config'] as Map<String, dynamic>?;
            if (topic == null || config == null) {
              _sendError(request, HttpStatus.badRequest, "Missing 'topic' or 'config'");
              return;
            }
            await database.saveUiConfig(topic: topic, config: config);
            _sendJson(request, {"status": "saved"});
            break;

          case '/ros/science_layout':
            final instance = request.uri.queryParameters['instance'] ?? 'default';
            await database.saveScienceLayout(body: body, instance: instance);
            _sendJson(request, {"status": "saved"});
            break;

          case '/ros/publish':
            final topic = body['topic'] as String?;
            final value = body['value'];
            final type = body['type'] as String? ?? 'std_msgs/msg/Float64';
            if (topic == null) {
              _sendError(request, HttpStatus.badRequest, "Missing 'topic'");
              return;
            }
            roverClient.publishRaw(topic, type, value);
            _sendJson(request, {"status": "success"});
            break;

          case '/ros/macro':
            final steps = body['steps'] as List?;
            if (steps == null || steps.isEmpty) {
              _sendError(request, HttpStatus.badRequest, "Macro steps missing");
              return;
            }
            // Execute in background
            _executeMacro(steps);
            _sendJson(request, {
              "status": "macro_started",
              "steps_count": steps.length,
            });
            break;

          default:
            _sendError(request, HttpStatus.notFound, "Endpoint not found");
        }
      } else if (request.method == 'DELETE') {
        final body = await _readJsonBody(request);
        switch (path) {
          case '/ros/saved_commands':
            final topic = body['topic'] as String?;
            final name = body['name'] as String?;
            if (topic == null || name == null) {
              _sendError(request, HttpStatus.badRequest, "Missing topic or name");
              return;
            }
            final deleted = await database.deleteCommand(topic: topic, name: name);
            if (deleted) {
              _sendJson(request, {"status": "success", "message": "Command '$name' deleted"});
            } else {
              _sendError(request, HttpStatus.notFound, "Command not found");
            }
            break;

          default:
            _sendError(request, HttpStatus.notFound, "Endpoint not found");
        }
      } else {
        _sendError(request, HttpStatus.methodNotAllowed, "Method not allowed");
      }
    } catch (e) {
      print("RovServer: Request handling exception: $e");
      _sendError(request, HttpStatus.internalServerError, e.toString());
    }
  }

  void _handleWebSocketConnection(WebSocket ws) {
    _wsClients.add(ws);
    print("RovServer: Client WebSocket connected. Total active clients: ${_wsClients.length}");

    // Send initial status immediately upon connection
    _sendWsMsg(ws, {
      "type": "status",
      "data": controlService.getStatus().toJson(),
      "timestamp": DateTime.now().toIso8601String(),
    });

    ws.listen((data) {
      if (data is String) {
        _handleIncomingWsMessage(ws, data);
      }
    }, onError: (err) {
      print("RovServer: Client WebSocket error: $err");
      _wsClients.remove(ws);
    }, onDone: () {
      print("RovServer: Client WebSocket closed.");
      _wsClients.remove(ws);
    });
  }

  void _handleIncomingWsMessage(WebSocket ws, String data) {
    try {
      final message = json.decode(data) as Map<String, dynamic>;
      final type = message['type'] as String?;

      switch (type) {
        case 'joystick':
          final x = (message['x'] ?? 0.0) as num;
          final y = (message['y'] ?? 0.0) as num;
          controlService.updateJoystickInput(x.toDouble(), y.toDouble());
          break;

        case 'joystick_release':
          controlService.releaseJoystickInput();
          break;

        case 'joystick_activate':
          controlService.isJoystickActive = true;
          break;

        case 'joystick_deactivate':
          controlService.isJoystickActive = false;
          controlService.publishStop();
          break;

        case 'ping':
          _sendWsMsg(ws, {
            "type": "pong",
            "timestamp": DateTime.now().toIso8601String(),
          });
          break;

        case 'request_state':
          _sendWsMsg(ws, {
            "type": "status",
            "data": controlService.getStatus().toJson(),
            "timestamp": DateTime.now().toIso8601String(),
          });
          break;

        case 'gamepad_event':
          final action = message['action'] as String? ?? 'move';
          final code = message['code'] as String? ?? '';
          final value = message['value'] != null ? (message['value'] as num).toDouble() : null;
          final axesMap = message['axes'] != null ? Map<String, double>.from(
              (message['axes'] as Map).map((k, v) => MapEntry(k.toString(), (v as num).toDouble()))
          ) : null;
          final pressedCodes = message['pressed_codes'] != null ? List<String>.from(message['pressed_codes'] as List) : null;

          if (action == 'move') {
            controlService.handleHidMove(code, value, axesMap);
          } else if (action == 'press' || action == 'release') {
            controlService.handleHidButton(code, action, value);
          } else if (action == 'state' && pressedCodes != null) {
            controlService.handleHidState(pressedCodes);
          }
          break;

        default:
          print("RovServer: Unregistered WS message type: $type");
      }
    } catch (e) {
      print("RovServer: Error processing incoming WS message: $e");
    }
  }

  void _broadcastState() {
    final statusMsg = {
      "type": "status",
      "data": controlService.getStatus().toJson(),
      "timestamp": DateTime.now().toIso8601String(),
    };
    final payload = json.encode(statusMsg);
    for (final ws in _wsClients) {
      try {
        ws.add(payload);
      } catch (_) {}
    }
  }

  void _sendWsMsg(WebSocket ws, Map<String, dynamic> msg) {
    try {
      ws.add(json.encode(msg));
    } catch (e) {
      print("RovServer: WS send failed: $e");
    }
  }

  Future<void> _executeMacro(List<dynamic> steps) async {
    print("RovServer: Executing macro sequence with ${steps.length} steps...");
    for (int i = 0; i < steps.length; i++) {
      try {
        final step = steps[i];
        if (step is! Map<String, dynamic>) continue;
        final action = step['action'] as String? ?? '';

        if (action == 'publish') {
          final topic = step['topic'] as String?;
          final value = step['value'];
          final type = step['type'] as String? ?? 'std_msgs/msg/Float64';
          if (topic != null) {
            roverClient.publishRaw(topic, type, value);
            print("Macro Step [${i + 1}]: Published to $topic");
          }
        } else if (action == 'wait_time' || action == 'delay') {
          final delay = (step['delay'] ?? step['seconds'] ?? 1.0) as num;
          await Future.delayed(Duration(milliseconds: (delay * 1000).toInt()));
          print("Macro Step [${i + 1}]: Delayed for $delay seconds");
        }
      } catch (e) {
        print("RovServer: Macro execution failed at step ${i + 1}: $e");
        break; // Abort on execution error
      }
    }
    print("RovServer: Macro execution finished.");
  }

  Future<Map<String, dynamic>> _readJsonBody(HttpRequest request) async {
    final content = await utf8.decoder.bind(request).join();
    if (content.trim().isEmpty) return {};
    return json.decode(content) as Map<String, dynamic>;
  }

  void _sendJson(HttpRequest request, Map<String, dynamic> data) async {
    request.response.headers.contentType = ContentType.json;
    request.response.write(json.encode(data));
    await request.response.close();
  }

  void _sendError(HttpRequest request, int statusCode, String message) async {
    request.response.statusCode = statusCode;
    request.response.headers.contentType = ContentType.json;
    request.response.write(json.encode({"error": message}));
    await request.response.close();
  }
}

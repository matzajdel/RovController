import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/io.dart';

class RoverClient {
  final String ip;
  final int port;

  WebSocketChannel? _channel;
  bool _isConnected = false;
  bool _isConnecting = false;
  bool _shouldReconnect = true;
  Timer? _reconnectTimer;

  final Set<String> _advertisedTopics = {};
  final Map<String, String> _activeSubscriptions = {};

  final StreamController<bool> _connectionStatusController = StreamController<bool>.broadcast();
  final StreamController<Map<String, dynamic>> _messageController = StreamController<Map<String, dynamic>>.broadcast();

  RoverClient({required this.ip, this.port = 9090});

  bool get isConnected => _isConnected;
  Stream<bool> get connectionStatusStream => _connectionStatusController.stream;
  Stream<Map<String, dynamic>> get messageStream => _messageController.stream;

  /// Starts the connection attempt and schedules automatic reconnection.
  void connect() {
    _shouldReconnect = true;
    _attemptConnect();
  }

  /// Disconnects from the WebSocket server and stops automatic reconnection.
  void disconnect() {
    _shouldReconnect = false;
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _setConnected(false);
  }

  void _setConnected(bool connected) {
    if (_isConnected != connected) {
      _isConnected = connected;
      _connectionStatusController.add(connected);
      print("RoverClient: Connection status changed to $connected");
    }
  }

  Future<void> _attemptConnect() async {
    if (_isConnected || _isConnecting) return;
    _isConnecting = true;
    print("RoverClient: Attempting connection to ws://$ip:$port...");

    try {
      // Direct native WebSocket connection to allow setting a connection timeout
      final ws = await WebSocket.connect('ws://$ip:$port').timeout(const Duration(seconds: 4));
      _channel = IOWebSocketChannel(ws);
      _setConnected(true);
      _isConnecting = false;

      // Reset advertised topics state since connection is fresh
      _advertisedTopics.clear();
      _resubscribeAll();

      _channel!.stream.listen(
        (data) {
          _handleIncomingMessage(data);
        },
        onError: (err) {
          print("RoverClient: Stream error: $err");
          _handleDisconnection();
        },
        onDone: () {
          print("RoverClient: Connection closed by rover.");
          _handleDisconnection();
        },
      );
    } catch (e) {
      print("RoverClient: Connection attempt failed: $e");
      _isConnecting = false;
      _handleDisconnection();
    }
  }

  void _handleDisconnection() {
    _setConnected(false);
    _channel = null;
    if (_shouldReconnect) {
      _reconnectTimer?.cancel();
      _reconnectTimer = Timer(const Duration(seconds: 3), () {
        _attemptConnect();
      });
    }
  }

  void _handleIncomingMessage(dynamic rawData) {
    try {
      if (rawData is String) {
        final decoded = json.decode(rawData) as Map<String, dynamic>;
        _messageController.add(decoded);
      }
    } catch (e) {
      print("RoverClient: Error decoding incoming message: $e");
    }
  }

  void _send(Map<String, dynamic> jsonMsg) {
    if (!_isConnected || _channel == null) return;
    try {
      _channel!.sink.add(json.encode(jsonMsg));
    } catch (e) {
      print("RoverClient: Error sending packet: $e");
    }
  }

  /// Sends an 'advertise' operation to ROSBridge if not already advertised.
  void advertise(String topic, String type) {
    if (_advertisedTopics.contains(topic)) return;
    _advertisedTopics.add(topic);
    _send({
      "op": "advertise",
      "topic": topic,
      "type": type,
    });
  }

  /// Publishes a raw map message payload to a given topic.
  void publish(String topic, String type, Map<String, dynamic> msg) {
    advertise(topic, type);
    _send({
      "op": "publish",
      "topic": topic,
      "msg": msg,
    });
  }

  /// Subscribes to a ROS topic. The client automatically re-subscribes upon connection.
  void subscribe(String topic, String type) {
    _activeSubscriptions[topic] = type;
    if (_isConnected) {
      _send({
        "op": "subscribe",
        "topic": topic,
        "type": type,
      });
    }
  }

  /// Unsubscribes from a ROS topic.
  void unsubscribe(String topic) {
    _activeSubscriptions.remove(topic);
    if (_isConnected) {
      _send({
        "op": "unsubscribe",
        "topic": topic,
      });
    }
  }

  void _resubscribeAll() {
    _activeSubscriptions.forEach((topic, type) {
      _send({
        "op": "subscribe",
        "topic": topic,
        "type": type,
      });
    });
  }

  /// Publishes arbitrary standard inputs by mapping basic dynamic Dart values to their ROS counterpart payloads.
  void publishRaw(String topic, String type, dynamic value) {
    Map<String, dynamic> msg;

    if (type.contains("MultiArray")) {
      List<dynamic> dataList;
      if (value is List) {
        dataList = value;
      } else {
        dataList = [value];
      }
      msg = {
        "layout": {"dim": [], "data_offset": 0},
        "data": dataList,
      };
    } else if (type.endsWith("Twist")) {
      if (value is Map) {
        msg = {
          "linear": {
            "x": (value["linear_x"] ?? value["linear"]?["x"] ?? 0.0) as double,
            "y": (value["linear_y"] ?? value["linear"]?["y"] ?? 0.0) as double,
            "z": (value["linear_z"] ?? value["linear"]?["z"] ?? 0.0) as double,
          },
          "angular": {
            "x": (value["angular_x"] ?? value["angular"]?["x"] ?? 0.0) as double,
            "y": (value["angular_y"] ?? value["angular"]?["y"] ?? 0.0) as double,
            "z": (value["angular_z"] ?? value["angular"]?["z"] ?? 0.0) as double,
          }
        };
      } else {
        msg = {
          "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
          "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
        };
      }
    } else {
      msg = {"data": value};
    }

    publish(topic, type, msg);
  }
}

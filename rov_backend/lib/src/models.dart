class JoystickCommand {
  final double x;
  final double y;
  final String? timestamp;

  JoystickCommand({
    required this.x,
    required this.y,
    this.timestamp,
  });

  factory JoystickCommand.fromJson(Map<String, dynamic> json) {
    return JoystickCommand(
      x: (json['x'] as num?)?.toDouble() ?? 0.0,
      y: (json['y'] as num?)?.toDouble() ?? 0.0,
      timestamp: json['timestamp'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'x': x,
      'y': y,
      if (timestamp != null) 'timestamp': timestamp,
    };
  }

  @override
  String toString() => 'JoystickCommand(x: $x, y: $y, timestamp: $timestamp)';
}

class Twist {
  final double linearX;
  final double linearY;
  final double linearZ;
  final double angularX;
  final double angularY;
  final double angularZ;

  Twist({
    this.linearX = 0.0,
    this.linearY = 0.0,
    this.linearZ = 0.0,
    this.angularX = 0.0,
    this.angularY = 0.0,
    this.angularZ = 0.0,
  });

  factory Twist.fromJson(Map<String, dynamic> json) {
    return Twist(
      linearX: (json['linear_x'] as num?)?.toDouble() ?? 0.0,
      linearY: (json['linear_y'] as num?)?.toDouble() ?? 0.0,
      linearZ: (json['linear_z'] as num?)?.toDouble() ?? 0.0,
      angularX: (json['angular_x'] as num?)?.toDouble() ?? 0.0,
      angularY: (json['angular_y'] as num?)?.toDouble() ?? 0.0,
      angularZ: (json['angular_z'] as num?)?.toDouble() ?? 0.0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'linear_x': linearX,
      'linear_y': linearY,
      'linear_z': linearZ,
      'angular_x': angularX,
      'angular_y': angularY,
      'angular_z': angularZ,
    };
  }

  @override
  String toString() {
    return 'Twist(linear: ($linearX, $linearY, $linearZ), angular: ($angularX, $angularY, $angularZ))';
  }
}

class CustomCommand {
  final String name;
  final String topic;
  final String type;
  final dynamic value;
  final bool isDefault;
  final List<String> labels;

  CustomCommand({
    required this.name,
    required this.topic,
    required this.type,
    required this.value,
    this.isDefault = false,
    this.labels = const [],
  });

  factory CustomCommand.fromJson(Map<String, dynamic> json, {String? topic}) {
    return CustomCommand(
      name: json['name'] as String? ?? '',
      topic: topic ?? (json['topic'] as String? ?? ''),
      type: json['type'] as String? ?? '',
      value: json['value'],
      isDefault: json['isDefault'] as bool? ?? false,
      labels: (json['labels'] as List?)?.map((e) => e.toString()).toList() ?? const [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'topic': topic,
      'type': type,
      'value': value,
      'isDefault': isDefault,
      'labels': labels,
    };
  }

  @override
  String toString() {
    return 'CustomCommand(name: $name, topic: $topic, type: $type, isDefault: $isDefault)';
  }
}

class RobotStatus {
  final bool connected;
  final Map<String, dynamic>? lastCommand;
  final String lastUpdate;

  RobotStatus({
    required this.connected,
    this.lastCommand,
    required this.lastUpdate,
  });

  factory RobotStatus.fromJson(Map<String, dynamic> json) {
    return RobotStatus(
      connected: json['connected'] as bool? ?? false,
      lastCommand: json['last_command'] as Map<String, dynamic>?,
      lastUpdate: json['last_update'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'connected': connected,
      if (lastCommand != null) 'last_command': lastCommand,
      'last_update': lastUpdate,
    };
  }

  @override
  String toString() => 'RobotStatus(connected: $connected, lastUpdate: $lastUpdate)';
}

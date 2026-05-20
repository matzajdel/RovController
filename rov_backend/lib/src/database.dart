import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as p;
import 'models.dart';

class RovDatabase {
  final String storagePath;
  late final File _commandsFile;
  late final File _uiConfigFile;

  Map<String, List<CustomCommand>> _commands = {};
  Map<String, dynamic> _uiConfig = {};

  RovDatabase({required this.storagePath}) {
    _commandsFile = File(p.join(storagePath, 'saved_commands.json'));
    _uiConfigFile = File(p.join(storagePath, 'saved_ui_config.json'));
  }

  /// Initializes the database by reading the JSON files from the filesystem.
  /// If the storage directory or files do not exist, they are created.
  Future<void> init() async {
    // Ensure the parent directory exists
    final dir = Directory(storagePath);
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    await _loadCommands();
    await _loadUiConfig();
  }

  Future<void> _loadCommands() async {
    try {
      if (await _commandsFile.exists()) {
        final content = await _commandsFile.readAsString();
        if (content.trim().isNotEmpty) {
          final Map<String, dynamic> decoded = json.decode(content);
          final Map<String, List<CustomCommand>> loaded = {};
          decoded.forEach((topic, list) {
            if (list is List) {
              loaded[topic] = list
                  .map((item) => CustomCommand.fromJson(item as Map<String, dynamic>, topic: topic))
                  .toList();
            }
          });
          _commands = loaded;
          return;
        }
      }
    } catch (e) {
      // Non-blocking warning
      print("Warning: Error loading saved commands: $e");
    }
    _commands = {};
  }

  Future<void> _loadUiConfig() async {
    try {
      if (await _uiConfigFile.exists()) {
        final content = await _uiConfigFile.readAsString();
        if (content.trim().isNotEmpty) {
          _uiConfig = json.decode(content) as Map<String, dynamic>;
          return;
        }
      }
    } catch (e) {
      // Non-blocking warning
      print("Warning: Error loading UI config: $e");
    }
    _uiConfig = {};
  }

  Future<void> _saveCommands() async {
    try {
      final Map<String, dynamic> toSave = {};
      _commands.forEach((topic, list) {
        toSave[topic] = list.map((cmd) => cmd.toJson()).toList();
      });
      // Pretty print JSON (indent 2) to maintain exact compatibility
      const encoder = JsonEncoder.withIndent('  ');
      await _commandsFile.writeAsString(encoder.convert(toSave));
    } catch (e) {
      print("Error: Failed to save commands to disk: $e");
      rethrow;
    }
  }

  Future<void> _saveUiConfig() async {
    try {
      const encoder = JsonEncoder.withIndent('  ');
      await _uiConfigFile.writeAsString(encoder.convert(_uiConfig));
    } catch (e) {
      print("Error: Failed to save UI config to disk: $e");
      rethrow;
    }
  }

  // --- CRUD for Saved Commands ---

  /// Retrieve all saved commands grouped by topic.
  Map<String, List<CustomCommand>> getSavedCommands() {
    return _commands;
  }

  /// Save a named command for a specific topic.
  /// If a command with the same name exists, it gets updated.
  /// If [isDefault] is true, resets all other commands for the same topic to not be default.
  Future<void> saveCommand({
    required String topic,
    required String name,
    required dynamic value,
    required String type,
    bool isDefault = false,
    List<String> labels = const [],
  }) async {
    if (!_commands.containsKey(topic)) {
      _commands[topic] = [];
    }

    // Remove existing command with the same name
    _commands[topic]!.removeWhere((cmd) => cmd.name == name);

    // Enforce single default per topic
    if (isDefault) {
      _commands[topic] = _commands[topic]!.map((cmd) {
        return CustomCommand(
          name: cmd.name,
          topic: cmd.topic,
          type: cmd.type,
          value: cmd.value,
          isDefault: false,
          labels: cmd.labels,
        );
      }).toList();
    }

    _commands[topic]!.add(CustomCommand(
      name: name,
      topic: topic,
      type: type,
      value: value,
      isDefault: isDefault,
      labels: labels,
    ));

    await _saveCommands();
  }

  /// Delete a saved command by topic and name.
  /// Returns true if a command was successfully deleted.
  Future<bool> deleteCommand({required String topic, required String name}) async {
    if (_commands.containsKey(topic)) {
      final initialLength = _commands[topic]!.length;
      _commands[topic]!.removeWhere((cmd) => cmd.name == name);
      if (_commands[topic]!.isEmpty) {
        _commands.remove(topic);
      }
      await _saveCommands();
      return _commands[topic]?.length != initialLength;
    }
    return false;
  }

  // --- CRUD for UI Config ---

  /// Get UI button configuration for all topics, or filtered by [topic] if provided.
  Map<String, dynamic> getUiConfig({String? topic}) {
    if (topic != null) {
      return _uiConfig[topic] as Map<String, dynamic>? ?? {};
    }
    return _uiConfig;
  }

  /// Save UI config settings for a specific topic.
  Future<void> saveUiConfig({required String topic, required Map<String, dynamic> config}) async {
    _uiConfig[topic] = config;
    await _saveUiConfig();
  }

  // --- CRUD for Science Layout ---

  /// Retrieve the saved Science Dashboard layout for a given instance.
  Future<Map<String, dynamic>> getScienceLayout({String instance = 'default'}) async {
    final filename = instance == 'default' ? 'science_layout.json' : 'science_layout_$instance.json';
    final file = File(p.join(storagePath, filename));
    try {
      if (await file.exists()) {
        final content = await file.readAsString();
        if (content.trim().isNotEmpty) {
          return json.decode(content) as Map<String, dynamic>;
        }
      }
    } catch (e) {
      print("Warning: Error loading science layout for $instance: $e");
    }
    return {};
  }

  /// Save the entire Science Dashboard layout for a given instance by merging it with the existing configuration.
  Future<void> saveScienceLayout({required Map<String, dynamic> body, String instance = 'default'}) async {
    final filename = instance == 'default' ? 'science_layout.json' : 'science_layout_$instance.json';
    final file = File(p.join(storagePath, filename));
    final existing = await getScienceLayout(instance: instance);
    existing.addAll(body);
    const encoder = JsonEncoder.withIndent('  ');
    await file.writeAsString(encoder.convert(existing));
  }
}

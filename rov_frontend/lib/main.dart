import 'package:flutter/material.dart';

import 'src/app_theme.dart';
import 'src/backend_controller.dart';
import 'src/screens/camera_screen.dart';
import 'src/screens/home_screen.dart';

void main() {
  runApp(const RovApp());
}

class RovApp extends StatefulWidget {
  const RovApp({super.key});

  @override
  State<RovApp> createState() => _RovAppState();
}

class _RovAppState extends State<RovApp> {
  late final BackendController _backendController;

  @override
  void initState() {
    super.initState();
    _backendController = BackendController();
  }

  @override
  void dispose() {
    _backendController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Rov Controller',
      theme: buildAppTheme(),
      routes: {
        '/': (_) => HomeScreen(controller: _backendController),
        '/camera': (_) => CameraScreen(controller: _backendController),
      },
    );
  }
}

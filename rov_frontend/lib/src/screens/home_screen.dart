import 'dart:async';
import 'package:flutter/material.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../backend_controller.dart';
import 'manipulator_screen.dart';
import 'power_screen.dart';
import '../widgets/command_log_panel.dart';

import '../widgets/rov_joystick.dart';
import '../widgets/wifi_connect_dialog.dart';

class HomeScreen extends StatefulWidget {
  final BackendController controller;

  const HomeScreen({super.key, required this.controller});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentScreen = 0;

  static const List<String> _screenTitles = [
    'Drive',
    'Manipulator',
    'Power',
  ];

  void _goToPreviousScreen() {
    setState(() {
      _currentScreen =
          (_currentScreen - 1 + _screenTitles.length) % _screenTitles.length;
    });
  }

  void _goToNextScreen() {
    setState(() {
      _currentScreen = (_currentScreen + 1) % _screenTitles.length;
    });
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final connected = widget.controller.connected;
        final demoMode = widget.controller.demoMode;
        final controlEnabled = widget.controller.controlEnabled;
        final colorScheme = Theme.of(context).colorScheme;

        return Scaffold(
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Column(
                children: [
                  _TopStatusBar(
                    connected: connected,
                    demoMode: demoMode,
                    colorScheme: colorScheme,
                    onDemoToggled: widget.controller.toggleDemoMode,
                    onConnectPressed: () async {
                      await showWifiConnectDialog(context, widget.controller);
                    },
                    onDisconnectPressed: widget.controller.disconnect,
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: Column(
                      children: [
                        Expanded(
                          child: IndexedStack(
                            index: _currentScreen,
                            children: [
                              _DriveScreen(
                                connected: connected,
                                controlEnabled: controlEnabled,
                                onChanged: widget.controller.setJoystick,
                                onReleased: widget.controller.releaseJoystick,
                                onOpenCamera: () {
                                  Navigator.of(context).pushNamed('/camera');
                                },
                              ),
                              ManipulatorScreen(
                                enabled: controlEnabled,
                                controller: widget.controller,
                              ),
                              PowerScreen(controller: widget.controller),
                            ],
                          ),
                        ),
                        if (demoMode) ...[
                          const SizedBox(height: 12),
                          CommandLogPanel(
                            entries: widget.controller.commandHistory,
                            onClear: widget.controller.clearCommandHistory,
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  _ScreenSwitcher(
                    title: _screenTitles[_currentScreen],
                    onPrevious: _goToPreviousScreen,
                    onNext: _goToNextScreen,
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                        backgroundColor: Theme.of(context).colorScheme.error,
                        foregroundColor: Theme.of(context).colorScheme.onError,
                      ),
                      onPressed: widget.controller.backendStarted
                          ? widget.controller.emergencyStop
                          : null,
                      icon: const Icon(Icons.power_settings_new),
                      label: const Text('Emergency Stop'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _DriveScreen extends StatefulWidget {
  final bool connected;
  final bool controlEnabled;
  final JoystickChanged onChanged;
  final VoidCallback onReleased;
  final VoidCallback onOpenCamera;

  const _DriveScreen({
    required this.connected,
    required this.controlEnabled,
    required this.onChanged,
    required this.onReleased,
    required this.onOpenCamera,
  });

  @override
  State<_DriveScreen> createState() => _DriveScreenState();
}

class _DriveScreenState extends State<_DriveScreen> {
  bool _imuEnabled = false;
  Offset _imuKnobOffset = Offset.zero;
  StreamSubscription<GyroscopeEvent>? _imuSubscription;

  void _handleImuEvent(GyroscopeEvent event) {
    // Gyroscope reports angular velocity. We integrate the current motion into
    // a stable joystick offset so the knob keeps following the phone motion.
    const step = 0.04;
    const deadzone = 0.02;

    final deltaX = event.y.abs() < deadzone ? 0.0 : event.y * step;
    final deltaY = event.x.abs() < deadzone ? 0.0 : -event.x * step;

    final nextX = (_imuKnobOffset.dx + deltaX).clamp(-0.65, 0.65);
    final nextY = (_imuKnobOffset.dy + deltaY).clamp(-0.65, 0.65);

    setState(() {
      _imuKnobOffset = Offset(nextX, nextY);
    });

    widget.onChanged(nextX / 0.65, -(nextY / 0.65));
  }

  void _toggleImu(bool value) {
    setState(() {
      _imuEnabled = value;
      if (!value) {
        _imuKnobOffset = Offset.zero;
      }
    });

    if (value) {
      _imuSubscription = gyroscopeEventStream().listen((event) {
        _handleImuEvent(event);
      });
    } else {
      _imuSubscription?.cancel();
      _imuSubscription = null;
      widget.onReleased();
    }
  }

  @override
  void dispose() {
    _imuSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Joystick and IMU are ALWAYS enabled — commands are silently dropped
    // by BackendController if not connected to the rover.
    return Column(
      children: [
        // IMU Toggle Switch
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Text(
              widget.connected ? 'IMU Steering' : 'IMU Steering (offline)',
              style: TextStyle(
                fontSize: 12,
                color: widget.connected ? null : Theme.of(context).colorScheme.tertiary,
              ),
            ),
            Switch(
              value: _imuEnabled,
              onChanged: _toggleImu,
              activeThumbColor: Theme.of(context).colorScheme.primary,
            ),
          ],
        ),
        Expanded(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: AspectRatio(
                aspectRatio: 1,
                child: RovJoystick(
                  enabled: true,
                  knobOffset: _imuEnabled ? _imuKnobOffset : null,
                  onChanged: widget.onChanged,
                  onReleased: widget.onReleased,
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        _ControlGrid(onOpenCamera: widget.onOpenCamera),
      ],
    );
  }
}

class _ScreenSwitcher extends StatelessWidget {
  final String title;
  final VoidCallback onPrevious;
  final VoidCallback onNext;

  const _ScreenSwitcher({
    required this.title,
    required this.onPrevious,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        IconButton(
          onPressed: onPrevious,
          icon: const Icon(Icons.keyboard_arrow_left),
          tooltip: 'Previous screen',
        ),
        Expanded(
          child: Text(
            title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
        IconButton(
          onPressed: onNext,
          icon: const Icon(Icons.keyboard_arrow_right),
          tooltip: 'Next screen',
        ),
      ],
    );
  }
}

class _TopStatusBar extends StatelessWidget {
  final bool connected;
  final bool demoMode;
  final ColorScheme colorScheme;
  final VoidCallback onDemoToggled;
  final VoidCallback onConnectPressed;
  final VoidCallback onDisconnectPressed;

  const _TopStatusBar({
    required this.connected,
    required this.demoMode,
    required this.colorScheme,
    required this.onDemoToggled,
    required this.onConnectPressed,
    required this.onDisconnectPressed,
  });

  @override
  Widget build(BuildContext context) {
    final statusText = connected ? 'Połączono z ROSBridge' : 'Rozłączono';
    final statusIcon = connected ? Icons.wifi : Icons.wifi_off;
    final statusColor = demoMode
      ? colorScheme.primary
        : connected
      ? colorScheme.tertiary
      : colorScheme.onSurface.withAlpha(120);

    return Card(
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            Icon(statusIcon, size: 18, color: statusColor),
            const SizedBox(width: 8),
            Text(
              demoMode ? 'Demo' : statusText,
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(color: statusColor),
            ),
            const Spacer(),
            TextButton.icon(
              onPressed: onDemoToggled,
              icon: Icon(demoMode ? Icons.play_circle : Icons.science, size: 16),
              label: Text(demoMode ? 'Demo on' : 'Demo off'),
            ),
            const SizedBox(width: 8),
            if (connected)
              OutlinedButton.icon(
                onPressed: onDisconnectPressed,
                icon: const Icon(Icons.wifi_off, size: 16),
                label: const Text('Rozłącz'),
              )
            else
              FilledButton.icon(
                onPressed: onConnectPressed,
                icon: const Icon(Icons.wifi_find, size: 16),
                label: const Text('Połącz'),
              ),
          ],
        ),
      ),
    );
  }
}

class _ControlGrid extends StatelessWidget {
  final VoidCallback onOpenCamera;

  const _ControlGrid({required this.onOpenCamera});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            Expanded(child: _PadButton(label: 'Lights', onPressed: () {})),
            const SizedBox(width: 12),
            Expanded(child: _PadButton(label: 'Horn', onPressed: () {})),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(child: _PadButton(label: 'Mode', onPressed: () {})),
            const SizedBox(width: 12),
            Expanded(child: _PadButton(label: 'Camera', onPressed: onOpenCamera)),
          ],
        ),
      ],
    );
  }
}

class _PadButton extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;

  const _PadButton({required this.label, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 52,
      child: OutlinedButton(
        onPressed: onPressed,
        child: Text(label),
      ),
    );
  }
}

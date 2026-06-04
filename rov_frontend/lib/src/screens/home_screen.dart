import 'package:flutter/material.dart';

import '../backend_controller.dart';
import 'manipulator_screen.dart';
import '../widgets/rov_joystick.dart';

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

        return Scaffold(
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Column(
                children: [
                  _TopStatusBar(
                    connected: connected,
                    onConnectPressed: () async {
                      await widget.controller.connect();
                    },
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: IndexedStack(
                      index: _currentScreen,
                      children: [
                        _DriveScreen(
                          connected: connected,
                          onChanged: widget.controller.setJoystick,
                          onReleased: widget.controller.releaseJoystick,
                          onOpenCamera: () {
                            Navigator.of(context).pushNamed('/camera');
                          },
                        ),
                        const ManipulatorScreen(enabled: true),
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

class _DriveScreen extends StatelessWidget {
  final bool connected;
  final JoystickChanged onChanged;
  final VoidCallback onReleased;
  final VoidCallback onOpenCamera;

  const _DriveScreen({
    required this.connected,
    required this.onChanged,
    required this.onReleased,
    required this.onOpenCamera,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: AspectRatio(
                aspectRatio: 1,
                child: RovJoystick(
                  enabled: connected,
                  onChanged: onChanged,
                  onReleased: onReleased,
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        _ControlGrid(onOpenCamera: onOpenCamera),
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
  final VoidCallback onConnectPressed;

  const _TopStatusBar(
      {required this.connected, required this.onConnectPressed});

  @override
  Widget build(BuildContext context) {
    final statusText = connected ? 'Connected' : 'Disconnected';
    final statusIcon = connected ? Icons.wifi : Icons.wifi_off;

    return Row(
      children: [
        Icon(statusIcon, size: 18),
        const SizedBox(width: 8),
        Text(statusText, style: Theme.of(context).textTheme.titleSmall),
        const Spacer(),
        FilledButton(
          onPressed: connected ? null : onConnectPressed,
          child: const Text('Connect'),
        ),
      ],
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
            Expanded(
                child: _PadButton(label: 'Camera', onPressed: onOpenCamera)),
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

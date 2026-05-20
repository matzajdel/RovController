import 'package:flutter/material.dart';

import '../backend_controller.dart';
import '../widgets/rov_joystick.dart';

class HomeScreen extends StatelessWidget {
  final BackendController controller;

  const HomeScreen({super.key, required this.controller});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final connected = controller.connected;

        return Scaffold(
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Column(
                children: [
                  _TopStatusBar(
                    connected: connected,
                    onConnectPressed: () async {
                      await controller.connect();
                    },
                  ),
                  const SizedBox(height: 12),
                  _ControlGrid(),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: () {
                            Navigator.of(context).pushNamed('/camera');
                          },
                          icon: const Icon(Icons.photo_camera_outlined),
                          label: const Text('Camera'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () {},
                          icon: const Icon(Icons.settings_outlined),
                          label: const Text('Settings'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 420),
                        child: AspectRatio(
                          aspectRatio: 1,
                          child: RovJoystick(
                            enabled: connected,
                            onChanged: controller.setJoystick,
                            onReleased: controller.releaseJoystick,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                        backgroundColor: Theme.of(context).colorScheme.error,
                        foregroundColor: Theme.of(context).colorScheme.onError,
                      ),
                      onPressed: controller.backendStarted ? controller.emergencyStop : null,
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

class _TopStatusBar extends StatelessWidget {
  final bool connected;
  final VoidCallback onConnectPressed;

  const _TopStatusBar({required this.connected, required this.onConnectPressed});

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
            Expanded(child: _PadButton(label: 'Reset', onPressed: () {})),
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

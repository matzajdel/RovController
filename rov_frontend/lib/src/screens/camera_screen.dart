import 'package:flutter/material.dart';

import '../backend_controller.dart';
import '../widgets/rov_joystick.dart';

class CameraScreen extends StatefulWidget {
  final BackendController controller;

  const CameraScreen({super.key, required this.controller});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  int _selected = 0;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final connected = widget.controller.connected;

        return Scaffold(
          appBar: AppBar(
            title: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Camera'),
                const SizedBox(height: 2),
                Text('Camera Stream View', style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Column(
                children: [
                  _CameraTabs(
                    selected: _selected,
                    onSelected: (idx) => setState(() => _selected = idx),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    height: 220,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Theme.of(context).dividerColor),
                    ),
                    child: Center(
                      child: connected
                          ? const SizedBox.shrink()
                          : Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text('Camera Offline', style: Theme.of(context).textTheme.titleMedium),
                                const SizedBox(height: 8),
                                Text('Connect first', style: Theme.of(context).textTheme.bodySmall),
                              ],
                            ),
                    ),
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
                            onChanged: widget.controller.setJoystick,
                            onReleased: widget.controller.releaseJoystick,
                          ),
                        ),
                      ),
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

class _CameraTabs extends StatelessWidget {
  final int selected;
  final ValueChanged<int> onSelected;

  const _CameraTabs({required this.selected, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    Widget buildButton(int idx, String top, String bottom) {
      final isSelected = selected == idx;
      void onPressed() => onSelected(idx);
      final child = Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(top),
          const SizedBox(height: 2),
          Text(bottom, style: Theme.of(context).textTheme.bodySmall),
        ],
      );

      return Expanded(
        child: SizedBox(
          height: 54,
          child: isSelected
              ? FilledButton(onPressed: onPressed, child: child)
              : OutlinedButton(onPressed: onPressed, child: child),
        ),
      );
    }

    return Row(
      children: [
        buildButton(0, '1', 'Front'),
        const SizedBox(width: 12),
        buildButton(1, '2', 'Rear'),
        const SizedBox(width: 12),
        buildButton(2, '3', 'Left'),
        const SizedBox(width: 12),
        buildButton(3, '4', 'Right'),
      ],
    );
  }
}

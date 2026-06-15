import 'dart:async';

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../backend_controller.dart';
import '../widgets/command_log_panel.dart';

import '../widgets/rov_joystick.dart';

class CameraScreen extends StatefulWidget {
  final BackendController controller;

  const CameraScreen({super.key, required this.controller});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  int _selected = 0;
  VideoPlayerController? _demoVideoController;
  Future<void>? _demoVideoInit;

  @override
  void initState() {
    super.initState();
    _demoVideoController = VideoPlayerController.asset(
      'Subway_surfer_gameplay_no_commentary.mp4',
    )
      ..setLooping(true)
      ..setVolume(0.0);
    _demoVideoInit = _demoVideoController!.initialize().then((_) {
      if (!mounted) return;
      _demoVideoController!.play();
      setState(() {});
    });
  }

  @override
  void dispose() {
    _demoVideoController?.dispose();
    super.dispose();
  }

  Widget _buildDemoVideo(BuildContext context) {
    final controller = _demoVideoController;
    if (controller == null) {
      return _buildDemoPlaceholder(context);
    }

    return FutureBuilder<void>(
      future: _demoVideoInit,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done || !controller.value.isInitialized) {
          return _buildDemoPlaceholder(context);
        }

        return ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: FittedBox(
            fit: BoxFit.cover,
            clipBehavior: Clip.hardEdge,
            child: SizedBox(
              width: controller.value.size.width,
              height: controller.value.size.height,
              child: VideoPlayer(controller),
            ),
          ),
        );
      },
    );
  }

  Widget _buildDemoPlaceholder(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.videocam, size: 42, color: Theme.of(context).colorScheme.primary),
        const SizedBox(height: 12),
        Text('Demo camera feed', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text('Wideo działa w pętli', style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final connected = widget.controller.connected;
        final demoMode = widget.controller.demoMode;
        final controlEnabled = widget.controller.controlEnabled;

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
                      child: demoMode
                          ? _buildDemoVideo(context)
                          : connected
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
                            enabled: controlEnabled,
                            onChanged: widget.controller.setJoystick,
                            onReleased: widget.controller.releaseJoystick,
                          ),
                        ),
                      ),
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

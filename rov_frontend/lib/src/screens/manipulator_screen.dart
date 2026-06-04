import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../widgets/rov_joystick.dart';

class ManipulatorScreen extends StatefulWidget {
  final bool enabled;

  const ManipulatorScreen({super.key, required this.enabled});

  @override
  State<ManipulatorScreen> createState() => _ManipulatorScreenState();
}

class _ManipulatorScreenState extends State<ManipulatorScreen> {
  double _axis1 = 0.0;
  double _axis2 = 0.0;
  double _axis3 = 0.0;
  double _axis4 = 0.0;
  double _axis5 = 0.0;
  double _axis6 = 0.0;

  void _onLeftJoystick(double x, double y) {
    setState(() {
      _axis1 = x;
      _axis2 = y;
    });
  }

  void _onRightJoystick(double x, double y) {
    setState(() {
      _axis3 = y;
      _axis4 = x;
    });
  }

  void _releaseLeftJoystick() {
    setState(() {
      _axis1 = 0.0;
      _axis2 = 0.0;
    });
  }

  void _releaseRightJoystick() {
    setState(() {
      _axis3 = 0.0;
      _axis4 = 0.0;
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Stack(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            children: [
              SizedBox(
                width: 74,
                child: _AxisSlider(
                  label: 'Axis 5',
                  value: _axis5,
                  enabled: widget.enabled,
                  onChanged: (value) {
                    setState(() {
                      _axis5 = value;
                    });
                  },
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _ArmPreview(
                  axis1: _axis1,
                  axis2: _axis2,
                  axis3: _axis3,
                  axis4: _axis4,
                  axis5: _axis5,
                  axis6: _axis6,
                  enabled: widget.enabled,
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                width: 74,
                child: _SpringGripControl(
                  label: 'Axis 6',
                  value: _axis6,
                  enabled: widget.enabled,
                  onChanged: (value) {
                    setState(() {
                      _axis6 = value;
                    });
                  },
                  onReleased: () {
                    setState(() {
                      _axis6 = 0.0;
                    });
                  },
                ),
              ),
            ],
          ),
        ),
        Positioned(
          left: 6,
          bottom: 4,
          child: SizedBox(
            width: 132,
            height: 132,
            child: Card(
              color: scheme.surface,
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(6),
                child: RovJoystick(
                  enabled: widget.enabled,
                  onChanged: _onLeftJoystick,
                  onReleased: _releaseLeftJoystick,
                ),
              ),
            ),
          ),
        ),
        Positioned(
          right: 6,
          bottom: 4,
          child: SizedBox(
            width: 132,
            height: 132,
            child: Card(
              color: scheme.surface,
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(6),
                child: RovJoystick(
                  enabled: widget.enabled,
                  onChanged: _onRightJoystick,
                  onReleased: _releaseRightJoystick,
                ),
              ),
            ),
          ),
        ),
        const Positioned(
          left: 14,
          bottom: 140,
          child: _ControlTag(text: 'A1 Base / A2 Shoulder'),
        ),
        const Positioned(
          right: 14,
          bottom: 140,
          child: _ControlTag(text: 'A3 Elbow / A4 Wrist'),
        ),
      ],
    );
  }
}

class _ControlTag extends StatelessWidget {
  final String text;

  const _ControlTag({required this.text});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        child: Text(
          text,
          style: Theme.of(context).textTheme.labelSmall,
        ),
      ),
    );
  }
}

class _AxisSlider extends StatelessWidget {
  final String label;
  final double value;
  final bool enabled;
  final ValueChanged<double> onChanged;

  const _AxisSlider({
    required this.label,
    required this.value,
    required this.enabled,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
        child: Column(
          children: [
            Text(label, style: Theme.of(context).textTheme.labelSmall),
            const SizedBox(height: 8),
            Expanded(
              child: RotatedBox(
                quarterTurns: 3,
                child: Slider(
                  min: -1,
                  max: 1,
                  value: value,
                  onChanged: enabled ? onChanged : null,
                ),
              ),
            ),
            Text(value.toStringAsFixed(2),
                style: Theme.of(context).textTheme.labelSmall),
          ],
        ),
      ),
    );
  }
}

class _SpringGripControl extends StatefulWidget {
  final String label;
  final double value;
  final bool enabled;
  final ValueChanged<double> onChanged;
  final VoidCallback onReleased;

  const _SpringGripControl({
    required this.label,
    required this.value,
    required this.enabled,
    required this.onChanged,
    required this.onReleased,
  });

  @override
  State<_SpringGripControl> createState() => _SpringGripControlState();
}

class _SpringGripControlState extends State<_SpringGripControl> {
  void _updateFromLocal(Offset localPosition, Size size) {
    final centerY = size.height / 2;
    final dy = (centerY - localPosition.dy) / centerY;
    widget.onChanged(dy.clamp(-1.0, 1.0));
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 12),
        child: Column(
          children: [
            Text(widget.label, style: Theme.of(context).textTheme.labelSmall),
            const SizedBox(height: 8),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final trackSize =
                      Size(constraints.maxWidth, constraints.maxHeight);

                  return GestureDetector(
                    onPanStart: widget.enabled
                        ? (details) =>
                            _updateFromLocal(details.localPosition, trackSize)
                        : null,
                    onPanUpdate: widget.enabled
                        ? (details) =>
                            _updateFromLocal(details.localPosition, trackSize)
                        : null,
                    onPanEnd:
                        widget.enabled ? (_) => widget.onReleased() : null,
                    onPanCancel: widget.enabled ? widget.onReleased : null,
                    child: CustomPaint(
                      painter: _SpringGripPainter(
                        value: widget.value,
                        enabled: widget.enabled,
                        scheme: Theme.of(context).colorScheme,
                      ),
                      child: const SizedBox.expand(),
                    ),
                  );
                },
              ),
            ),
            Text(widget.value.toStringAsFixed(2),
                style: Theme.of(context).textTheme.labelSmall),
          ],
        ),
      ),
    );
  }
}

class _SpringGripPainter extends CustomPainter {
  final double value;
  final bool enabled;
  final ColorScheme scheme;

  const _SpringGripPainter({
    required this.value,
    required this.enabled,
    required this.scheme,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final trackRect = RRect.fromRectAndRadius(
      Rect.fromLTWH(size.width * 0.25, 0, size.width * 0.5, size.height),
      const Radius.circular(999),
    );

    final trackPaint = Paint()
      ..color =
          enabled ? scheme.surfaceContainerHighest : scheme.surfaceContainer;
    canvas.drawRRect(trackRect, trackPaint);

    final markerY = center.dy - (value * (size.height * 0.42));
    final marker = Offset(center.dx, markerY);

    final springPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = scheme.outline;

    final path = Path();
    path.moveTo(center.dx, center.dy);
    for (var i = 1; i <= 8; i++) {
      final t = i / 8;
      final y = center.dy + (markerY - center.dy) * t;
      final x = center.dx + (i.isEven ? 6 : -6);
      path.lineTo(x, y);
    }
    path.lineTo(marker.dx, marker.dy);
    canvas.drawPath(path, springPaint);

    final knobPaint = Paint()
      ..color = enabled ? scheme.primary : scheme.outline;
    canvas.drawCircle(marker, size.width * 0.18, knobPaint);
  }

  @override
  bool shouldRepaint(covariant _SpringGripPainter oldDelegate) {
    return oldDelegate.value != value ||
        oldDelegate.enabled != enabled ||
        oldDelegate.scheme != scheme;
  }
}

class _ArmPreview extends StatelessWidget {
  final double axis1;
  final double axis2;
  final double axis3;
  final double axis4;
  final double axis5;
  final double axis6;
  final bool enabled;

  const _ArmPreview({
    required this.axis1,
    required this.axis2,
    required this.axis3,
    required this.axis4,
    required this.axis5,
    required this.axis6,
    required this.enabled,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _ArmPreviewPainter(
                axis1: axis1,
                axis2: axis2,
                axis3: axis3,
                axis4: axis4,
                axis5: axis5,
                axis6: axis6,
                enabled: enabled,
                scheme: Theme.of(context).colorScheme,
              ),
            ),
          ),
          Positioned(
            left: 12,
            top: 10,
            child: Text(
              'Manipulator Model',
              style: Theme.of(context).textTheme.labelMedium,
            ),
          ),
          Positioned(
            left: 12,
            top: 30,
            child: Text(
              'A1 ${axis1.toStringAsFixed(2)}  A2 ${axis2.toStringAsFixed(2)}\n'
              'A3 ${axis3.toStringAsFixed(2)}  A4 ${axis4.toStringAsFixed(2)}\n'
              'A5 ${axis5.toStringAsFixed(2)}  A6 ${axis6.toStringAsFixed(2)}',
              style: Theme.of(context).textTheme.labelSmall,
            ),
          ),
        ],
      ),
    );
  }
}

class _ArmPreviewPainter extends CustomPainter {
  final double axis1;
  final double axis2;
  final double axis3;
  final double axis4;
  final double axis5;
  final double axis6;
  final bool enabled;
  final ColorScheme scheme;

  const _ArmPreviewPainter({
    required this.axis1,
    required this.axis2,
    required this.axis3,
    required this.axis4,
    required this.axis5,
    required this.axis6,
    required this.enabled,
    required this.scheme,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final backgroundPaint = Paint()..color = scheme.surface;
    canvas.drawRect(Offset.zero & size, backgroundPaint);

    final gridPaint = Paint()
      ..color = scheme.outlineVariant.withValues(alpha: 0.35)
      ..strokeWidth = 1;
    for (double x = 0; x <= size.width; x += 28) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (double y = 0; y <= size.height; y += 28) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    final chassisPaint = Paint()..color = scheme.surfaceContainerHighest;
    final chassisRect = RRect.fromRectAndRadius(
      Rect.fromLTWH(size.width * 0.26, size.height * 0.72, size.width * 0.48,
          size.height * 0.16),
      const Radius.circular(14),
    );
    canvas.drawRRect(chassisRect, chassisPaint);

    final wheelPaint = Paint()..color = scheme.outlineVariant;
    canvas.drawCircle(
        Offset(size.width * 0.3, size.height * 0.9), 13, wheelPaint);
    canvas.drawCircle(
        Offset(size.width * 0.7, size.height * 0.9), 13, wheelPaint);

    final base = Offset(size.width * 0.5, size.height * 0.7);
    final basePaint = Paint()
      ..color = enabled ? scheme.primary : scheme.outline;
    canvas.drawCircle(base, 16, basePaint);

    final yaw = axis1 * 0.6;
    final yawPointer = base + Offset(math.cos(yaw), math.sin(yaw)) * 24;
    final yawPaint = Paint()
      ..color = scheme.onPrimary
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(base, yawPointer, yawPaint);

    final shoulderAngle = (-math.pi / 2) + axis2 * 0.9;
    final elbowAngle = shoulderAngle + (axis3 * 1.0);
    final wristAngle = elbowAngle + (axis4 * 0.9);

    final l1 = size.shortestSide * 0.18;
    final l2 = size.shortestSide * 0.16;
    final l3 = size.shortestSide * 0.1;

    final p1 =
        base + Offset(math.cos(shoulderAngle), math.sin(shoulderAngle)) * l1;
    final p2 = p1 + Offset(math.cos(elbowAngle), math.sin(elbowAngle)) * l2;
    final p3 = p2 + Offset(math.cos(wristAngle), math.sin(wristAngle)) * l3;

    final armPaint = Paint()
      ..color = enabled ? scheme.primary : scheme.outline
      ..strokeWidth = 9
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(base, p1, armPaint);
    canvas.drawLine(p1, p2, armPaint);
    canvas.drawLine(p2, p3, armPaint);

    final jointPaint = Paint()..color = scheme.onPrimary;
    canvas.drawCircle(p1, 4.5, jointPaint);
    canvas.drawCircle(p2, 4.5, jointPaint);
    canvas.drawCircle(p3, 4.5, jointPaint);

    final rot = wristAngle + axis5 * 0.9;
    final gripOpen = (axis6 + 1.0) / 2.0;
    final gripGap = 8 + (18 * gripOpen);
    final fingerLen = 24.0;
    final fingerPaint = Paint()
      ..color = scheme.secondary
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;

    final normal = Offset(-math.sin(rot), math.cos(rot));
    final dir = Offset(math.cos(rot), math.sin(rot));

    final leftBase = p3 + normal * (gripGap / 2);
    final rightBase = p3 - normal * (gripGap / 2);

    canvas.drawLine(leftBase, leftBase + dir * fingerLen, fingerPaint);
    canvas.drawLine(rightBase, rightBase + dir * fingerLen, fingerPaint);
  }

  @override
  bool shouldRepaint(covariant _ArmPreviewPainter oldDelegate) {
    return oldDelegate.axis1 != axis1 ||
        oldDelegate.axis2 != axis2 ||
        oldDelegate.axis3 != axis3 ||
        oldDelegate.axis4 != axis4 ||
        oldDelegate.axis5 != axis5 ||
        oldDelegate.axis6 != axis6 ||
        oldDelegate.enabled != enabled ||
        oldDelegate.scheme != scheme;
  }
}

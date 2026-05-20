import 'dart:math' as math;

import 'package:flutter/material.dart';

typedef JoystickChanged = void Function(double x, double y);

class RovJoystick extends StatefulWidget {
  final bool enabled;
  final JoystickChanged onChanged;
  final VoidCallback onReleased;

  const RovJoystick({
    super.key,
    required this.enabled,
    required this.onChanged,
    required this.onReleased,
  });

  @override
  State<RovJoystick> createState() => _RovJoystickState();
}

class _RovJoystickState extends State<RovJoystick> {
  Offset _knob = Offset.zero;

  void _update(Offset localPos, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final delta = localPos - center;
    final radius = math.min(size.width, size.height) / 2;
    final maxKnob = radius * 0.65;

    final distance = delta.distance;
    final clamped = distance <= maxKnob ? delta : delta * (maxKnob / (distance == 0 ? 1 : distance));

    final x = (clamped.dx / maxKnob).clamp(-1.0, 1.0);
    // Screen coordinates have +Y going down; invert so pushing up => +1.0.
    final y = (-clamped.dy / maxKnob).clamp(-1.0, 1.0);

    setState(() {
      _knob = clamped;
    });

    widget.onChanged(x.toDouble(), y.toDouble());
  }

  void _release() {
    setState(() {
      _knob = Offset.zero;
    });
    widget.onReleased();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = Size(constraints.maxWidth, constraints.maxHeight);

        return GestureDetector(
          onPanStart: widget.enabled ? (d) => _update(d.localPosition, size) : null,
          onPanUpdate: widget.enabled ? (d) => _update(d.localPosition, size) : null,
          onPanEnd: widget.enabled ? (_) => _release() : null,
          onPanCancel: widget.enabled ? _release : null,
          child: CustomPaint(
            painter: _JoystickPainter(
              knobOffset: _knob,
              enabled: widget.enabled,
              colorScheme: Theme.of(context).colorScheme,
              dividerColor: Theme.of(context).dividerColor,
            ),
            child: const SizedBox.expand(),
          ),
        );
      },
    );
  }
}

class _JoystickPainter extends CustomPainter {
  final Offset knobOffset;
  final bool enabled;
  final ColorScheme colorScheme;
  final Color dividerColor;

  _JoystickPainter({
    required this.knobOffset,
    required this.enabled,
    required this.colorScheme,
    required this.dividerColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2;

    final ringPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = radius * 0.05
      ..color = enabled ? colorScheme.primary : dividerColor;

    final basePaint = Paint()
      ..style = PaintingStyle.fill
      ..color = colorScheme.surface;

    canvas.drawCircle(center, radius, basePaint);
    canvas.drawCircle(center, radius, ringPaint);

    final knobRadius = radius * 0.18;
    final knobCenter = center + knobOffset;

    final knobPaint = Paint()
      ..style = PaintingStyle.fill
      ..color = enabled ? colorScheme.primary : dividerColor;

    canvas.drawCircle(knobCenter, knobRadius, knobPaint);
  }

  @override
  bool shouldRepaint(covariant _JoystickPainter oldDelegate) {
    return oldDelegate.knobOffset != knobOffset ||
        oldDelegate.enabled != enabled ||
        oldDelegate.colorScheme != colorScheme ||
        oldDelegate.dividerColor != dividerColor;
  }
}

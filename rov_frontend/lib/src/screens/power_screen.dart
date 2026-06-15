import 'package:flutter/material.dart';
import '../backend_controller.dart';
import '../widgets/command_log_panel.dart';

// ---------------------------------------------------------------------------
// Circuit definitions — match the rover's /string_topic naming convention
// (format: "CX-ON" / "CX-OFF" where X is the circuit number)
// ---------------------------------------------------------------------------
class _Circuit {
  final String id; // e.g. "C1"
  final String label; // human-readable name
  final String description;
  final IconData icon;
  final Color color;

  const _Circuit({
    required this.id,
    required this.label,
    required this.description,
    required this.icon,
    required this.color,
  });
}

const List<_Circuit> _kCircuits = [
  _Circuit(
    id: 'C1',
    label: 'Obwód 1',
    description: 'Circuit 1',
    icon: Icons.electrical_services,
    color: Color(0xFF6366F1), // indigo
  ),
  _Circuit(
    id: 'C2',
    label: 'Obwód 2',
    description: 'Circuit 2',
    icon: Icons.electrical_services,
    color: Color(0xFF0EA5E9), // sky blue
  ),
  _Circuit(
    id: 'C3',
    label: 'Obwód 3',
    description: 'Circuit 3',
    icon: Icons.electrical_services,
    color: Color(0xFF10B981), // emerald
  ),
  _Circuit(
    id: 'C4',
    label: 'Obwód 4',
    description: 'Circuit 4',
    icon: Icons.electrical_services,
    color: Color(0xFFF59E0B), // amber
  ),
  _Circuit(
    id: 'C5',
    label: 'Obwód 5',
    description: 'Circuit 5',
    icon: Icons.electrical_services,
    color: Color(0xFFEF4444), // red
  ),
  _Circuit(
    id: 'C6',
    label: 'Obwód 6',
    description: 'Circuit 6',
    icon: Icons.electrical_services,
    color: Color(0xFFEC4899), // pink
  ),
  _Circuit(
    id: 'C7',
    label: 'Obwód 7',
    description: 'Circuit 7',
    icon: Icons.electrical_services,
    color: Color(0xFF8B5CF6), // violet
  ),
  _Circuit(
    id: 'C8',
    label: 'Obwód 8',
    description: 'Circuit 8',
    icon: Icons.electrical_services,
    color: Color(0xFF14B8A6), // teal
  ),
  _Circuit(
    id: 'C9',
    label: 'Obwód 9',
    description: 'Circuit 9',
    icon: Icons.electrical_services,
    color: Color(0xFFF97316), // orange
  ),
  _Circuit(
    id: 'C10',
    label: 'Obwód 10',
    description: 'Circuit 10',
    icon: Icons.electrical_services,
    color: Color(0xFF06B6D4), // cyan
  ),
  _Circuit(
    id: 'C11',
    label: 'Obwód 11',
    description: 'Circuit 11',
    icon: Icons.electrical_services,
    color: Color(0xFFA3E635), // lime
  ),
  _Circuit(
    id: 'C12',
    label: 'Obwód 12',
    description: 'Circuit 12',
    icon: Icons.electrical_services,
    color: Color(0xFFFB7185), // rose
  ),
];

// ---------------------------------------------------------------------------
// Screen widget
// ---------------------------------------------------------------------------
class PowerScreen extends StatefulWidget {
  final BackendController controller;

  const PowerScreen({super.key, required this.controller});

  @override
  State<PowerScreen> createState() => _PowerScreenState();
}

class _PowerScreenState extends State<PowerScreen>
    with TickerProviderStateMixin {
  /// Tracks which circuits are currently ON
  final Map<String, bool> _circuitState = {
    for (final c in _kCircuits) c.id: false,
  };

  /// Tracks circuits currently being toggled (to show loading state)
  final Set<String> _pending = {};

  /// Animation controllers per circuit (for the glow pulse when active)
  late final Map<String, AnimationController> _pulseControllers;
  late final Map<String, Animation<double>> _pulseAnimations;

  // Last action feedback
  String? _lastAction;

  @override
  void initState() {
    super.initState();

    _pulseControllers = {};
    _pulseAnimations = {};

    for (final c in _kCircuits) {
      final ctrl = AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 1200),
      )..repeat(reverse: true);

      _pulseControllers[c.id] = ctrl;
      _pulseAnimations[c.id] = Tween<double>(begin: 0.3, end: 1.0).animate(
        CurvedAnimation(parent: ctrl, curve: Curves.easeInOut),
      );
    }
  }

  @override
  void dispose() {
    for (final ctrl in _pulseControllers.values) {
      ctrl.dispose();
    }
    super.dispose();
  }

  Future<void> _toggle(String circuitId) async {
    if (_pending.contains(circuitId)) return;

    final willBeOn = !(_circuitState[circuitId] ?? false);
    final message = willBeOn ? '$circuitId-ON' : '$circuitId-OFF';

    setState(() {
      _pending.add(circuitId);
    });

    // Publish to ROS topic /string_topic with type std_msgs/msg/String
    widget.controller.publishPowerCircuit(message);

    // Small artificial delay for UX feedback
    await Future.delayed(const Duration(milliseconds: 150));

    if (mounted) {
      setState(() {
        _circuitState[circuitId] = willBeOn;
        _pending.remove(circuitId);
        _lastAction = message;
      });
    }
  }

  Future<void> _allOff() async {
    for (final c in _kCircuits) {
      if (_circuitState[c.id] == true) {
        widget.controller.publishPowerCircuit('${c.id}-OFF');
        await Future.delayed(const Duration(milliseconds: 30));
      }
    }
    if (mounted) {
      setState(() {
        for (final c in _kCircuits) {
          _circuitState[c.id] = false;
        }
        _lastAction = 'ALL-OFF';
      });
    }
  }

  Future<void> _allOn() async {
    for (final c in _kCircuits) {
      if (_circuitState[c.id] == false) {
        widget.controller.publishPowerCircuit('${c.id}-ON');
        await Future.delayed(const Duration(milliseconds: 30));
      }
    }
    if (mounted) {
      setState(() {
        for (final c in _kCircuits) {
          _circuitState[c.id] = true;
        }
        _lastAction = 'ALL-ON';
      });
    }
  }

  int get _activeCount =>
      _circuitState.values.where((v) => v).length;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final demoMode = widget.controller.demoMode;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ── Header bar ──────────────────────────────────────────────────────
        _PowerHeader(
          activeCount: _activeCount,
          totalCount: _kCircuits.length,
          onAllOff: _allOff,
          onAllOn: _allOn,
          colorScheme: colorScheme,
        ),

        const SizedBox(height: 16),

        // ── Circuit grid ────────────────────────────────────────────────────
        Expanded(
          child: GridView.builder(
            padding: const EdgeInsets.only(bottom: 8),
            itemCount: _kCircuits.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: 1.15,
            ),
            itemBuilder: (context, index) {
              final circuit = _kCircuits[index];
              final isOn = _circuitState[circuit.id] ?? false;
              final isPending = _pending.contains(circuit.id);

              return _CircuitCard(
                circuit: circuit,
                isOn: isOn,
                isPending: isPending,
                pulseAnimation: _pulseAnimations[circuit.id]!,
                onTap: () => _toggle(circuit.id),
              );
            },
          ),
        ),

        // ── Status bar ──────────────────────────────────────────────────────
        if (_lastAction != null) ...[
          const SizedBox(height: 8),
          _StatusFeedback(action: _lastAction!),
        ],

        if (demoMode) ...[
          const SizedBox(height: 12),
          CommandLogPanel(
            entries: widget.controller.commandHistory,
            onClear: widget.controller.clearCommandHistory,
          ),
        ],

        const SizedBox(height: 8),

        // ── ROS info footer ─────────────────────────────────────────────────
        _RosInfoFooter(colorScheme: colorScheme),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Sub-widgets
// ---------------------------------------------------------------------------

class _PowerHeader extends StatelessWidget {
  final int activeCount;
  final int totalCount;
  final VoidCallback onAllOff;
  final VoidCallback onAllOn;
  final ColorScheme colorScheme;

  const _PowerHeader({
    required this.activeCount,
    required this.totalCount,
    required this.onAllOff,
    required this.onAllOn,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    final allOn = activeCount == totalCount;

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        gradient: LinearGradient(
          colors: activeCount > 0
              ? [
                  const Color(0xFF1a1f3c),
                  const Color(0xFF0f1729),
                ]
              : [
                  const Color(0xFF1a1a2e),
                  const Color(0xFF0d0d1a),
                ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: Border.all(
          color: activeCount > 0
              ? const Color(0xFF6366F1).withAlpha(100)
              : Colors.white.withAlpha(20),
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          // Power icon with pulse
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: activeCount > 0
                  ? const Color(0xFF6366F1).withAlpha(50)
                  : Colors.white.withAlpha(15),
              border: Border.all(
                color: activeCount > 0
                    ? const Color(0xFF6366F1).withAlpha(150)
                    : Colors.white.withAlpha(30),
              ),
            ),
            child: Icon(
              Icons.bolt,
              color: activeCount > 0
                  ? const Color(0xFF818CF8)
                  : Colors.white38,
              size: 24,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Zarządzanie obwodami',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.3,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '$activeCount / $totalCount aktywnych',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: activeCount > 0
                        ? const Color(0xFF818CF8)
                        : Colors.white38,
                  ),
                ),
              ],
            ),
          ),
          // Quick action buttons
          Row(
            children: [
              _QuickButton(
                label: 'WYŁ',
                icon: Icons.power_off_outlined,
                color: Colors.red.shade400,
                onPressed: onAllOff,
              ),
              const SizedBox(width: 8),
              _QuickButton(
                label: 'ZAŁ',
                icon: Icons.power_outlined,
                color: const Color(0xFF10B981),
                onPressed: onAllOn,
                filled: allOn,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _QuickButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback onPressed;
  final bool filled;

  const _QuickButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onPressed,
    this.filled = false,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: filled ? color.withAlpha(220) : color.withAlpha(30),
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: color.withAlpha(120)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 14, color: filled ? Colors.white : color),
              const SizedBox(width: 4),
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: filled ? Colors.white : color,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CircuitCard extends StatelessWidget {
  final _Circuit circuit;
  final bool isOn;
  final bool isPending;
  final Animation<double> pulseAnimation;
  final VoidCallback onTap;

  const _CircuitCard({
    required this.circuit,
    required this.isOn,
    required this.isPending,
    required this.pulseAnimation,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = circuit.color;

    return AnimatedBuilder(
      animation: pulseAnimation,
      builder: (context, child) {
        final glowOpacity = isOn ? (pulseAnimation.value * 0.35) : 0.0;
        final borderOpacity = isOn ? (0.4 + pulseAnimation.value * 0.4) : 0.15;

        return Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            boxShadow: isOn
                ? [
                    BoxShadow(
                      color: color.withValues(alpha: glowOpacity),
                      blurRadius: 20,
                      spreadRadius: 4,
                    )
                  ]
                : [],
          ),
          child: Material(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(18),
            child: InkWell(
              onTap: isPending ? null : onTap,
              borderRadius: BorderRadius.circular(18),
              splashColor: color.withAlpha(60),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOut,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: isOn
                        ? [
                            color.withAlpha(55),
                            color.withAlpha(25),
                          ]
                        : [
                            const Color(0xFF161B2E),
                            const Color(0xFF0E1120),
                          ],
                  ),
                  border: Border.all(
                    color: color.withValues(alpha: borderOpacity),
                    width: isOn ? 1.5 : 1.0,
                  ),
                ),
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Top row: icon + status indicator
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: isOn
                                ? color.withAlpha(60)
                                : Colors.white.withAlpha(12),
                            border: Border.all(
                              color: isOn
                                  ? color.withAlpha(150)
                                  : Colors.white.withAlpha(25),
                            ),
                          ),
                          child: isPending
                              ? Padding(
                                  padding: const EdgeInsets.all(10),
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: color,
                                  ),
                                )
                              : Icon(
                                  circuit.icon,
                                  color: isOn ? color : Colors.white30,
                                  size: 20,
                                ),
                        ),
                        // ON/OFF badge
                        AnimatedContainer(
                          duration: const Duration(milliseconds: 200),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(20),
                            color: isOn
                                ? color.withAlpha(60)
                                : Colors.white.withAlpha(12),
                            border: Border.all(
                              color: isOn
                                  ? color.withAlpha(150)
                                  : Colors.white.withAlpha(30),
                            ),
                          ),
                          child: Text(
                            isOn ? 'ZAŁ' : 'WYŁ',
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 0.8,
                              color: isOn ? color : Colors.white38,
                            ),
                          ),
                        ),
                      ],
                    ),

                    const Spacer(),

                    // Circuit ID
                    Text(
                      circuit.id,
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: isOn ? color : Colors.white54,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      circuit.label,
                      style: TextStyle(
                        fontSize: 12,
                        color: isOn
                            ? color.withAlpha(200)
                            : Colors.white30,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _StatusFeedback extends StatelessWidget {
  final String action;

  const _StatusFeedback({required this.action});

  @override
  Widget build(BuildContext context) {
    final isOn = action.endsWith('-ON') || action == 'ALL-ON';
    final color = isOn ? const Color(0xFF10B981) : Colors.red.shade400;

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: Container(
        key: ValueKey(action),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          color: color.withAlpha(25),
          border: Border.all(color: color.withAlpha(80)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isOn ? Icons.check_circle_outline : Icons.cancel_outlined,
              size: 14,
              color: color,
            ),
            const SizedBox(width: 6),
            Text(
              'Wysłano: $action → /string_topic',
              style: TextStyle(
                fontSize: 11,
                color: color,
                fontFamily: 'monospace',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RosInfoFooter extends StatelessWidget {
  final ColorScheme colorScheme;

  const _RosInfoFooter({required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        color: Colors.white.withAlpha(8),
        border: Border.all(color: Colors.white.withAlpha(18)),
      ),
      child: Row(
        children: [
          Icon(Icons.router_outlined,
              size: 13, color: Colors.white.withAlpha(80)),
          const SizedBox(width: 6),
          const Text(
            'ROS topic: /string_topic  |  type: std_msgs/msg/String  |  format: CX-ON / CX-OFF',
            style: TextStyle(
              fontSize: 10,
              color: Colors.white38,
              fontFamily: 'monospace',
            ),
          ),
        ],
      ),
    );
  }
}

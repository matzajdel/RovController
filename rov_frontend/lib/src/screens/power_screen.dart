import 'package:flutter/material.dart';

import '../backend_controller.dart';
import '../widgets/command_log_panel.dart';
import '../widgets/panel_shell.dart';

class _Circuit {
  final String id;
  final String label;
  final String description;
  final IconData icon;

  const _Circuit({
    required this.id,
    required this.label,
    required this.description,
    required this.icon,
  });
}

const List<_Circuit> _kCircuits = [
  _Circuit(id: 'C1', label: 'Obwód 1', description: 'Circuit 1', icon: Icons.electrical_services),
  _Circuit(id: 'C2', label: 'Obwód 2', description: 'Circuit 2', icon: Icons.electrical_services),
  _Circuit(id: 'C3', label: 'Obwód 3', description: 'Circuit 3', icon: Icons.electrical_services),
  _Circuit(id: 'C4', label: 'Obwód 4', description: 'Circuit 4', icon: Icons.electrical_services),
  _Circuit(id: 'C5', label: 'Obwód 5', description: 'Circuit 5', icon: Icons.electrical_services),
  _Circuit(id: 'C6', label: 'Obwód 6', description: 'Circuit 6', icon: Icons.electrical_services),
  _Circuit(id: 'C7', label: 'Obwód 7', description: 'Circuit 7', icon: Icons.electrical_services),
  _Circuit(id: 'C8', label: 'Obwód 8', description: 'Circuit 8', icon: Icons.electrical_services),
  _Circuit(id: 'C9', label: 'Obwód 9', description: 'Circuit 9', icon: Icons.electrical_services),
  _Circuit(id: 'C10', label: 'Obwód 10', description: 'Circuit 10', icon: Icons.electrical_services),
  _Circuit(id: 'C11', label: 'Obwód 11', description: 'Circuit 11', icon: Icons.electrical_services),
  _Circuit(id: 'C12', label: 'Obwód 12', description: 'Circuit 12', icon: Icons.electrical_services),
];

class PowerScreen extends StatefulWidget {
  final BackendController controller;

  const PowerScreen({super.key, required this.controller});

  @override
  State<PowerScreen> createState() => _PowerScreenState();
}

class _PowerScreenState extends State<PowerScreen>
    with TickerProviderStateMixin {
  final Map<String, bool> _circuitState = {
    for (final circuit in _kCircuits) circuit.id: false,
  };

  final Set<String> _pending = {};
  late final Map<String, AnimationController> _pulseControllers;
  late final Map<String, Animation<double>> _pulseAnimations;
  String? _lastAction;

  @override
  void initState() {
    super.initState();
    _pulseControllers = {};
    _pulseAnimations = {};

    for (final circuit in _kCircuits) {
      final controller = AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 1200),
      )..repeat(reverse: true);

      _pulseControllers[circuit.id] = controller;
      _pulseAnimations[circuit.id] = Tween<double>(begin: 0.3, end: 1.0).animate(
        CurvedAnimation(parent: controller, curve: Curves.easeInOut),
      );
    }
  }

  @override
  void dispose() {
    for (final controller in _pulseControllers.values) {
      controller.dispose();
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

    widget.controller.publishPowerCircuit(message);

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
    for (final circuit in _kCircuits) {
      if (_circuitState[circuit.id] == true) {
        widget.controller.publishPowerCircuit('${circuit.id}-OFF');
        await Future.delayed(const Duration(milliseconds: 30));
      }
    }

    if (mounted) {
      setState(() {
        for (final circuit in _kCircuits) {
          _circuitState[circuit.id] = false;
        }
        _lastAction = 'ALL-OFF';
      });
    }
  }

  Future<void> _allOn() async {
    for (final circuit in _kCircuits) {
      if (_circuitState[circuit.id] == false) {
        widget.controller.publishPowerCircuit('${circuit.id}-ON');
        await Future.delayed(const Duration(milliseconds: 30));
      }
    }

    if (mounted) {
      setState(() {
        for (final circuit in _kCircuits) {
          _circuitState[circuit.id] = true;
        }
        _lastAction = 'ALL-ON';
      });
    }
  }

  int get _activeCount => _circuitState.values.where((value) => value).length;

  @override
  Widget build(BuildContext context) {
    final demoMode = widget.controller.demoMode;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _PowerHeader(
          activeCount: _activeCount,
          totalCount: _kCircuits.length,
          onAllOff: _allOff,
          onAllOn: _allOn,
        ),
        const SizedBox(height: 16),
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
        const _RosInfoFooter(),
      ],
    );
  }
}

class _PowerHeader extends StatelessWidget {
  final int activeCount;
  final int totalCount;
  final VoidCallback onAllOff;
  final VoidCallback onAllOn;

  const _PowerHeader({
    required this.activeCount,
    required this.totalCount,
    required this.onAllOff,
    required this.onAllOn,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final allOn = activeCount == totalCount;

    return PanelShell(
      emphasized: activeCount > 0,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: activeCount > 0
                  ? colorScheme.primary.withAlpha(50)
                  : colorScheme.outline.withAlpha(18),
              border: Border.all(
                color: activeCount > 0
                    ? colorScheme.primary.withAlpha(150)
                    : colorScheme.outline.withAlpha(40),
              ),
            ),
            child: Icon(
              Icons.bolt,
              color: activeCount > 0
                  ? colorScheme.primary
                  : colorScheme.onSurface.withAlpha(110),
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
                        color: colorScheme.onSurface,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 0.3,
                      ),
                ),
                const SizedBox(height: 2),
                Text(
                  '$activeCount / $totalCount aktywnych',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: activeCount > 0
                            ? colorScheme.primary
                            : colorScheme.onSurface.withAlpha(110),
                      ),
                ),
              ],
            ),
          ),
          Row(
            children: [
              OutlinedButton.icon(
                onPressed: onAllOff,
                icon: const Icon(Icons.power_off_outlined, size: 16),
                label: const Text('WYŁ'),
              ),
              const SizedBox(width: 8),
              FilledButton.icon(
                onPressed: allOn ? null : onAllOn,
                icon: const Icon(Icons.power_outlined, size: 16),
                label: const Text('ZAŁ'),
              ),
            ],
          ),
        ],
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
    final colorScheme = Theme.of(context).colorScheme;

    return AnimatedBuilder(
      animation: pulseAnimation,
      builder: (context, child) {
        return Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
          ),
          child: Material(
            color: isOn ? colorScheme.primaryContainer : colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(18),
            child: InkWell(
              onTap: isPending ? null : onTap,
              borderRadius: BorderRadius.circular(18),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOut,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: colorScheme.outlineVariant,
                    width: 1,
                  ),
                ),
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: isOn ? colorScheme.primary : colorScheme.surface,
                            border: Border.all(
                              color: colorScheme.outlineVariant,
                            ),
                          ),
                          child: isPending
                              ? Padding(
                                  padding: const EdgeInsets.all(10),
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: colorScheme.primary,
                                  ),
                                )
                              : Icon(
                                  circuit.icon,
                                  size: 20,
                                  color: isOn ? colorScheme.onPrimary : colorScheme.onSurfaceVariant,
                                ),
                        ),
                        AnimatedContainer(
                          duration: const Duration(milliseconds: 200),
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(20),
                            color: isOn ? colorScheme.primaryContainer : colorScheme.surface,
                            border: Border.all(
                              color: colorScheme.outlineVariant,
                            ),
                          ),
                          child: Text(
                            isOn ? 'ZAŁ' : 'WYŁ',
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 0.8,
                              color: isOn ? colorScheme.onPrimaryContainer : colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const Spacer(),
                    Text(
                      circuit.id,
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: isOn ? colorScheme.onPrimaryContainer : colorScheme.onSurface,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      circuit.label,
                      style: TextStyle(
                        fontSize: 12,
                        color: isOn ? colorScheme.onPrimaryContainer : colorScheme.onSurfaceVariant,
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
    final colorScheme = Theme.of(context).colorScheme;
    final isOn = action.endsWith('-ON') || action == 'ALL-ON';
    final color = isOn ? colorScheme.primary : colorScheme.error;

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
  const _RosInfoFooter();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return PanelShell(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          Icon(Icons.router_outlined, size: 13, color: colorScheme.onSurface.withAlpha(120)),
          const SizedBox(width: 6),
          Text(
            'ROS topic: /string_topic  |  type: std_msgs/msg/String  |  format: CX-ON / CX-OFF',
            style: TextStyle(
              fontSize: 10,
              color: colorScheme.onSurface.withAlpha(110),
              fontFamily: 'monospace',
            ),
          ),
        ],
      ),
    );
  }
}

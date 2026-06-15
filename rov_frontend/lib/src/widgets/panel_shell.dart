import 'package:flutter/material.dart';

class PanelShell extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final bool emphasized;

  const PanelShell({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.emphasized = false,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: Theme.of(context).colorScheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
      ),
      child: Padding(
        padding: padding,
        child: child,
      ),
    );
  }
}

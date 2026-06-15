import 'package:flutter/material.dart';

import '../backend_controller.dart';

class CommandLogPanel extends StatelessWidget {
  final List<CommandLogEntry> entries;
  final VoidCallback onClear;

  const CommandLogPanel({
    super.key,
    required this.entries,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: theme.colorScheme.surface,
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(Icons.receipt_long, size: 18, color: theme.colorScheme.primary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Wysłane komendy',
                  style: theme.textTheme.titleSmall,
                ),
              ),
              TextButton(
                onPressed: entries.isEmpty ? null : onClear,
                child: const Text('Wyczyść'),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (entries.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(
                'Brak komend do pokazania.',
                style: theme.textTheme.bodySmall,
              ),
            )
          else
            SizedBox(
              height: 170,
              child: ListView.separated(
                itemCount: entries.length,
                separatorBuilder: (_, __) => const SizedBox(height: 8),
                itemBuilder: (context, index) {
                  final entry = entries[index];
                  return _CommandRow(entry: entry);
                },
              ),
            ),
        ],
      ),
    );
  }
}

class _CommandRow extends StatelessWidget {
  final CommandLogEntry entry;

  const _CommandRow({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface.withAlpha(200),
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  entry.title,
                  style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
              Text(
                _formatTime(entry.timestamp),
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            entry.details,
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  String _formatTime(DateTime timestamp) {
    final hours = timestamp.hour.toString().padLeft(2, '0');
    final minutes = timestamp.minute.toString().padLeft(2, '0');
    final seconds = timestamp.second.toString().padLeft(2, '0');
    return '$hours:$minutes:$seconds';
  }
}

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import '../backend_controller.dart';
import '../services/wifi_service.dart';

Future<String?> showWifiConnectDialog(
  BuildContext context,
  BackendController controller,
) {
  return showDialog<String>(
    context: context,
    barrierDismissible: true,
    builder: (_) => WifiConnectDialog(controller: controller),
  );
}

class WifiConnectDialog extends StatefulWidget {
  final BackendController controller;

  const WifiConnectDialog({super.key, required this.controller});

  @override
  State<WifiConnectDialog> createState() => _WifiConnectDialogState();
}

class _WifiConnectDialogState extends State<WifiConnectDialog> {
  List<WifiNetwork> _networks = [];
  bool _loading = false;
  bool _connecting = false;
  String? _scanError;
  String? _connectError;
  final TextEditingController _ipController = TextEditingController(
    text: BackendController.defaultRoverIp,
  );

  @override
  void initState() {
    super.initState();
    if (WifiService.isPlatformSupported) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _scan());
    }
  }

  @override
  void dispose() {
    _ipController.dispose();
    super.dispose();
  }

  Future<void> _scan() async {
    setState(() {
      _loading = true;
      _scanError = null;
      _networks = [];
    });

    try {
      final hasPermission = await WifiService.hasPermission();
      if (!hasPermission) {
        final granted = await WifiService.requestPermission();
        if (!granted) {
          if (mounted) {
            setState(() {
              _loading = false;
              _scanError = 'Uprawnienie lokalizacji jest wymagane do skanowania WiFi.';
            });
          }
          return;
        }
      }

      final networks = await WifiService.scan();
      if (mounted) {
        setState(() {
          _networks = networks;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _scanError = 'Nie udało się przeskanować sieci WiFi: $e';
        });
      }
    }
  }

  Future<void> _connect() async {
    final ip = _ipController.text.trim();
    if (ip.isEmpty) return;

    setState(() {
      _connecting = true;
      _connectError = null;
    });

    try {
      await widget.controller.connect(roverIp: ip);
      if (mounted) Navigator.of(context).pop(ip);
    } catch (e) {
      if (mounted) {
        setState(() {
          _connecting = false;
          _connectError = 'Błąd połączenia z łazikiem: $e';
        });
      }
    }
  }

  void _openWifiSettings() async {
    if (kIsWeb) return;
    await Permission.locationWhenInUse.request();
    await openAppSettings();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
              child: Row(
                children: [
                  const Icon(Icons.wifi_find_outlined),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Połącz z łazikiem', style: theme.textTheme.titleLarge),
                        const SizedBox(height: 2),
                        Text(
                          'Wybierz sieć WiFi i podaj IP backendu łazika.',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (WifiService.isPlatformSupported) ...[
                      Text('Dostępne sieci WiFi', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 12),
                      if (_loading)
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.symmetric(vertical: 24),
                            child: CircularProgressIndicator(),
                          ),
                        )
                      else if (_scanError != null)
                        _InfoBox(
                          icon: Icons.info_outline,
                          message: _scanError!,
                        )
                      else if (_networks.isEmpty)
                        Text('Nie znaleziono sieci WiFi.', style: theme.textTheme.bodyMedium)
                      else
                        Card(
                          elevation: 0,
                          child: Column(
                            children: [
                              for (final network in _networks)
                                ListTile(
                                  leading: const Icon(Icons.wifi),
                                  title: Text(network.ssid),
                                  subtitle: Text(
                                    network.bars != null
                                        ? 'Siła sygnału: ${network.bars}/4'
                                        : 'Sieć wykryta przez skanowanie',
                                  ),
                                  onTap: () {
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(
                                        content: Text(
                                          'Połącz się z siecią "${network.ssid}" w ustawieniach systemu, a potem wpisz IP backendu.',
                                        ),
                                        action: SnackBarAction(
                                          label: 'Ustawienia WiFi',
                                          onPressed: _openWifiSettings,
                                        ),
                                      ),
                                    );
                                  },
                                ),
                            ],
                          ),
                        ),
                      const SizedBox(height: 20),
                    ] else ...[
                      _InfoBox(
                        icon: Icons.info_outline,
                        message:
                            'Skanowanie WiFi niedostępne w przeglądarce. Połącz się z siecią łazika ręcznie i podaj jego IP poniżej.',
                      ),
                      const SizedBox(height: 20),
                    ],
                    Text('IP backendu łazika (port 2137)', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _ipController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.router_outlined),
                        hintText: '192.168.2.50',
                      ),
                    ),
                    if (_connectError != null) ...[
                      const SizedBox(height: 12),
                      _ErrorBox(message: _connectError!),
                    ],
                  ],
                ),
              ),
            ),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.all(20),
              child: SizedBox(
                width: double.infinity,
                height: 48,
                child: FilledButton.icon(
                  onPressed: _connecting ? null : _connect,
                  icon: _connecting
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.cable),
                  label: Text(_connecting ? 'Łączenie...' : 'Połącz z łazikiem'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoBox extends StatelessWidget {
  final IconData icon;
  final String message;

  const _InfoBox({required this.icon, required this.message});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(icon),
            const SizedBox(width: 12),
            Expanded(child: Text(message)),
          ],
        ),
      ),
    );
  }
}

class _ErrorBox extends StatelessWidget {
  final String message;

  const _ErrorBox({required this.message});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: Theme.of(context).colorScheme.error),
            const SizedBox(width: 12),
            Expanded(child: Text(message)),
          ],
        ),
      ),
    );
  }
}

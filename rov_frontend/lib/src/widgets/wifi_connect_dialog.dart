import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import '../backend_controller.dart';
import '../services/wifi_service.dart';

/// Shows the WiFi + rover connect dialog.
///
/// Returns the rover IP that was used to connect, or null if cancelled.
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

// ---------------------------------------------------------------------------
// Main dialog widget
// ---------------------------------------------------------------------------

class WifiConnectDialog extends StatefulWidget {
  final BackendController controller;

  const WifiConnectDialog({super.key, required this.controller});

  @override
  State<WifiConnectDialog> createState() => _WifiConnectDialogState();
}

class _WifiConnectDialogState extends State<WifiConnectDialog>
    with SingleTickerProviderStateMixin {
  // WiFi scan state
  WifiScanState _scanState = WifiScanState.idle;
  List<WifiNetwork> _networks = [];
  String? _scanError;

  // Rover IP
  final _ipController = TextEditingController(
    text: BackendController.defaultRoverIp,
  );

  // Connecting state
  bool _connecting = false;
  String? _connectError;

  // Scan animation
  late AnimationController _spinCtrl;

  @override
  void initState() {
    super.initState();
    _spinCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();

    // Auto-scan if supported
    if (WifiService.isPlatformSupported) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _startScan());
    }
  }

  @override
  void dispose() {
    _spinCtrl.dispose();
    _ipController.dispose();
    super.dispose();
  }

  Future<void> _startScan() async {
    setState(() {
      _scanState = WifiScanState.requesting;
      _scanError = null;
      _networks = [];
    });

    // Check / request permission
    final hasPermission = await WifiService.hasPermission();
    if (!hasPermission) {
      setState(() => _scanState = WifiScanState.requesting);
      final granted = await WifiService.requestPermission();
      if (!granted) {
        setState(() {
          _scanState = WifiScanState.denied;
          _scanError =
              'Uprawnienie lokalizacji jest wymagane do skanowania sieci WiFi.';
        });
        return;
      }
    }

    setState(() => _scanState = WifiScanState.scanning);

    try {
      final networks = await WifiService.scan();
      if (mounted) {
        setState(() {
          _networks = networks;
          _scanState = WifiScanState.done;
        });
      }
    } on WifiScanException catch (e) {
      if (mounted) {
        setState(() {
          _scanState = WifiScanState.done;
          _scanError = e.userMessage;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _scanState = WifiScanState.done;
          _scanError = 'Błąd skanowania: $e';
        });
      }
    }
  }

  Future<void> _connectToRover() async {
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

  void _selectNetwork(WifiNetwork network) {
    // Auto-fill IP based on common rover subnet conventions
    // The rover is typically at .1 or .100 of the hotspot gateway
    setState(() {
      // Keep IP as-is – user may change it manually
    });

    // Show snackbar guiding user to connect via system
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Połącz się z siecią "${network.ssid}" w ustawieniach WiFi systemu, '
          'a następnie wróć i naciśnij "Połącz z łazikiem".',
        ),
        action: SnackBarAction(
          label: 'Ustawienia WiFi',
          onPressed: _openSystemWifiSettings,
        ),
        duration: const Duration(seconds: 6),
      ),
    );
  }

  Future<void> _openSystemWifiSettings() async {
    // Opens Android's WiFi settings panel
    if (kIsWeb) return;
    try {
      await Permission.locationWhenInUse.request(); // ensure context
      // Use intent to open WiFi settings
      // On Android this opens the system WiFi picker
      // ignore: avoid_print
      print('Opening WiFi settings...');
      // openAppSettings() opens app-specific settings, not ideal here
      // We use a direct intent approach via method channel or fallback
      // For now, openAppSettings as a fallback
      await openAppSettings();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 32),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 480, maxHeight: 640),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF1a1f3c), Color(0xFF0d1020)],
          ),
          border: Border.all(
            color: const Color(0xFF6366F1).withAlpha(80),
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF6366F1).withAlpha(40),
              blurRadius: 32,
              spreadRadius: 4,
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildHeader(),
            Flexible(child: _buildBody()),
            _buildFooter(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 20, 12, 16),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: Colors.white.withAlpha(18)),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF6366F1).withAlpha(40),
              border: Border.all(
                  color: const Color(0xFF6366F1).withAlpha(120)),
            ),
            child: const Icon(Icons.wifi_find, color: Color(0xFF818CF8), size: 20),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Połącz z łazikiem',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  'Wybierz sieć WiFi i podaj IP łazika',
                  style: TextStyle(color: Colors.white38, fontSize: 11),
                ),
              ],
            ),
          ),
          IconButton(
            icon:
                const Icon(Icons.close, color: Colors.white38, size: 20),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ── WiFi Networks section ─────────────────────────────────────────
          if (WifiService.isPlatformSupported) ...[
            _buildSectionLabel('Dostępne sieci WiFi', Icons.wifi),
            const SizedBox(height: 10),
            _buildNetworksList(),
            const SizedBox(height: 6),
            _buildScanFooter(),
            const SizedBox(height: 20),
          ] else ...[
            _buildWebFallbackNote(),
            const SizedBox(height: 20),
          ],

          // ── Rover IP section ──────────────────────────────────────────────
          _buildSectionLabel('IP łazika (ROSBridge)', Icons.router),
          const SizedBox(height: 10),
          _buildIpField(),

          if (_connectError != null) ...[
            const SizedBox(height: 8),
            _buildErrorBanner(_connectError!),
          ],
        ],
      ),
    );
  }

  Widget _buildSectionLabel(String label, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 14, color: const Color(0xFF818CF8)),
        const SizedBox(width: 6),
        Text(
          label,
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.bold,
            letterSpacing: 0.8,
            color: Color(0xFF818CF8),
          ),
        ),
      ],
    );
  }

  Widget _buildNetworksList() {
    if (_scanState == WifiScanState.idle ||
        _scanState == WifiScanState.requesting ||
        _scanState == WifiScanState.scanning) {
      return _buildScanningIndicator();
    }

    if (_scanError != null) {
      return _buildErrorBanner(_scanError!);
    }

    if (_networks.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          color: Colors.white.withAlpha(8),
          border: Border.all(color: Colors.white.withAlpha(18)),
        ),
        child: const Text(
          'Nie znaleziono sieci WiFi.',
          style: TextStyle(color: Colors.white38, fontSize: 12),
          textAlign: TextAlign.center,
        ),
      );
    }

    return Container(
      constraints: const BoxConstraints(maxHeight: 260),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withAlpha(18)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: ListView.separated(
          shrinkWrap: true,
          itemCount: _networks.length,
          separatorBuilder: (_, __) =>
              Divider(height: 1, color: Colors.white.withAlpha(12)),
          itemBuilder: (context, i) =>
              _NetworkTile(network: _networks[i], onTap: _selectNetwork),
        ),
      ),
    );
  }

  Widget _buildScanningIndicator() {
    final label = _scanState == WifiScanState.requesting
        ? 'Prośba o uprawnienia...'
        : 'Skanowanie sieci...';

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        color: Colors.white.withAlpha(8),
        border: Border.all(color: Colors.white.withAlpha(18)),
      ),
      child: Column(
        children: [
          RotationTransition(
            turns: _spinCtrl,
            child: const Icon(Icons.wifi_find,
                color: Color(0xFF818CF8), size: 28),
          ),
          const SizedBox(height: 10),
          Text(label,
              style: const TextStyle(color: Colors.white54, fontSize: 12)),
        ],
      ),
    );
  }

  Widget _buildScanFooter() {
    return Row(
      children: [
        if (_scanState == WifiScanState.done)
          Text(
            '${_networks.length} sieci znalezionych',
            style: const TextStyle(color: Colors.white38, fontSize: 10),
          ),
        const Spacer(),
        GestureDetector(
          onTap: _scanState == WifiScanState.scanning ||
                  _scanState == WifiScanState.requesting
              ? null
              : _startScan,
          child: Row(
            children: [
              Icon(
                Icons.refresh,
                size: 13,
                color: _scanState == WifiScanState.scanning
                    ? Colors.white24
                    : const Color(0xFF818CF8),
              ),
              const SizedBox(width: 4),
              Text(
                'Skanuj ponownie',
                style: TextStyle(
                  fontSize: 11,
                  color: _scanState == WifiScanState.scanning
                      ? Colors.white24
                      : const Color(0xFF818CF8),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildWebFallbackNote() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        color: const Color(0xFF1e293b),
        border:
            Border.all(color: const Color(0xFF475569).withAlpha(100)),
      ),
      child: const Row(
        children: [
          Icon(Icons.info_outline, size: 16, color: Color(0xFF94A3B8)),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              'Skanowanie WiFi niedostępne w przeglądarce. '
              'Połącz się z siecią łazika ręcznie i podaj jego IP poniżej.',
              style: TextStyle(
                fontSize: 11,
                color: Color(0xFF94A3B8),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildIpField() {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        color: Colors.white.withAlpha(8),
        border: Border.all(color: const Color(0xFF6366F1).withAlpha(60)),
      ),
      child: TextField(
        controller: _ipController,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        style:
            const TextStyle(color: Colors.white, fontFamily: 'monospace'),
        decoration: const InputDecoration(
          contentPadding:
              EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          border: InputBorder.none,
          hintText: '192.168.2.100',
          hintStyle: TextStyle(color: Colors.white24),
          prefixIcon: Icon(Icons.lan_outlined,
              color: Color(0xFF818CF8), size: 18),
        ),
      ),
    );
  }

  Widget _buildErrorBanner(String message) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        color: Colors.red.withAlpha(25),
        border: Border.all(color: Colors.red.withAlpha(80)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, size: 14, color: Colors.redAccent),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(fontSize: 11, color: Colors.redAccent),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFooter() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 20),
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(color: Colors.white.withAlpha(18)),
        ),
      ),
      child: SizedBox(
        width: double.infinity,
        height: 48,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: _connecting
                ? const Color(0xFF4338CA)
                : const Color(0xFF6366F1),
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          onPressed: _connecting ? null : _connectToRover,
          icon: _connecting
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Icon(Icons.cable, size: 18),
          label: Text(
            _connecting ? 'Łączenie...' : 'Połącz z łazikiem',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Network list tile
// ---------------------------------------------------------------------------

class _NetworkTile extends StatelessWidget {
  final WifiNetwork network;
  final void Function(WifiNetwork) onTap;

  const _NetworkTile({required this.network, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => onTap(network),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(
            children: [
              // Signal bars icon
              _SignalIcon(bars: network.bars, is5GHz: network.is5GHz),
              const SizedBox(width: 12),
              // SSID + meta
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      network.ssid,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${network.is5GHz ? "5 GHz" : "2.4 GHz"} · ${network.signalPercent}%',
                      style: const TextStyle(
                        color: Colors.white38,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ),
              // Lock icon for secured networks
              if (network.isSecured)
                const Icon(Icons.lock_outline,
                    size: 14, color: Colors.white38),
              const SizedBox(width: 4),
              const Icon(Icons.arrow_forward_ios,
                  size: 12, color: Colors.white24),
            ],
          ),
        ),
      ),
    );
  }
}

class _SignalIcon extends StatelessWidget {
  final int bars; // 1–4
  final bool is5GHz;

  const _SignalIcon({required this.bars, required this.is5GHz});

  @override
  Widget build(BuildContext context) {
    Color barColor(int bar) {
      if (bar > bars) return Colors.white12;
      if (bars >= 3) return const Color(0xFF10B981); // green
      if (bars == 2) return const Color(0xFFF59E0B); // yellow
      return Colors.red.shade400; // red
    }

    return SizedBox(
      width: 22,
      height: 22,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: List.generate(4, (i) {
          final bar = i + 1;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            width: 4,
            height: 4.0 + bar * 3.5,
            decoration: BoxDecoration(
              color: barColor(bar),
              borderRadius: BorderRadius.circular(1),
            ),
          );
        }),
      ),
    );
  }
}

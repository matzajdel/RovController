import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:wifi_scan/wifi_scan.dart';

/// Represents a single scanned WiFi access point.
class WifiNetwork {
  final String ssid;
  final String bssid;
  final int signalLevel; // dBm, e.g. -45
  final String capabilities; // e.g. "[WPA2-PSK-CCMP][ESS]"
  final int frequency; // MHz

  WifiNetwork({
    required this.ssid,
    required this.bssid,
    required this.signalLevel,
    required this.capabilities,
    required this.frequency,
  });

  /// Signal quality 0–100 (converted from dBm)
  int get signalPercent {
    if (signalLevel >= -50) return 100;
    if (signalLevel <= -100) return 0;
    return 2 * (signalLevel + 100);
  }

  /// Number of signal bars (1–4)
  int get bars {
    final pct = signalPercent;
    if (pct >= 75) return 4;
    if (pct >= 50) return 3;
    if (pct >= 25) return 2;
    return 1;
  }

  bool get isSecured =>
      capabilities.contains('WPA') ||
      capabilities.contains('WEP') ||
      capabilities.contains('PSK');

  bool get is5GHz => frequency >= 5000;
}

/// Possible states of the WiFi scan
enum WifiScanState { idle, requesting, scanning, done, unsupported, denied }

class WifiService {
  /// Whether WiFi scanning is supported on the current platform.
  static bool get isPlatformSupported {
    if (kIsWeb) return false;
    return Platform.isAndroid || Platform.isLinux;
  }

  /// Requests location permission (required for WiFi scanning on Android 6+).
  /// Returns true if permission is granted.
  static Future<bool> requestPermission() async {
    if (!isPlatformSupported) return false;
    final status = await Permission.locationWhenInUse.request();
    return status.isGranted;
  }

  /// Checks if location permission is already granted.
  static Future<bool> hasPermission() async {
    if (!isPlatformSupported) return false;
    return await Permission.locationWhenInUse.isGranted;
  }

  /// Starts a WiFi scan and returns the results.
  ///
  /// Throws [WifiScanException] if not supported or permission denied.
  static Future<List<WifiNetwork>> scan() async {
    if (!isPlatformSupported) return [];

    final wifi = WiFiScan.instance;

    // Check if scanning is available
    final canStart = await wifi.canStartScan(askPermissions: false);
    if (canStart != CanStartScan.yes) {
      // Try requesting permissions first
      final granted = await requestPermission();
      if (!granted) throw WifiScanException('location_denied');

      final retry = await wifi.canStartScan(askPermissions: false);
      if (retry != CanStartScan.yes) {
        throw WifiScanException('scan_unavailable');
      }
    }

    // Trigger a fresh scan
    await wifi.startScan();

    // Get results (may include cached results from last scan)
    final canGet = await wifi.canGetScannedResults(askPermissions: false);
    if (canGet != CanGetScannedResults.yes) {
      throw WifiScanException('cannot_get_results');
    }

    final results = await wifi.getScannedResults();

    // Convert to our model, filter out empty SSIDs
    return results
        .where((ap) => ap.ssid.isNotEmpty)
        .map((ap) => WifiNetwork(
              ssid: ap.ssid,
              bssid: ap.bssid,
              signalLevel: ap.level,
              capabilities: ap.capabilities,
              frequency: ap.frequency,
            ))
        .toList()
      ..sort((a, b) => b.signalLevel.compareTo(a.signalLevel));
  }
}

class WifiScanException implements Exception {
  final String code;
  WifiScanException(this.code);

  String get userMessage {
    switch (code) {
      case 'location_denied':
        return 'Wymagane jest uprawnienie lokalizacji do skanowania WiFi.';
      case 'scan_unavailable':
        return 'Skanowanie WiFi jest niedostępne na tym urządzeniu.';
      case 'cannot_get_results':
        return 'Nie można pobrać wyników skanowania.';
      default:
        return 'Błąd skanowania WiFi: $code';
    }
  }
}

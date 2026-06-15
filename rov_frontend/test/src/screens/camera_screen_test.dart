import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rov_frontend/src/backend_controller.dart';
import 'package:rov_frontend/src/screens/camera_screen.dart';
import 'package:rov_frontend/src/widgets/command_log_panel.dart';
import 'package:rov_frontend/src/widgets/rov_joystick.dart';
import 'package:video_player/video_player.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

class _FakeBackendController extends BackendController {
  bool _connected;
  bool _demoMode;
  List<CommandLogEntry> _history;

  double? lastJoystickX;
  double? lastJoystickY;
  int releaseCount = 0;
  int clearCount = 0;

  _FakeBackendController({
    bool connected = false,
    bool demoMode = false,
    List<CommandLogEntry> history = const [],
  }) : _connected = connected,
       _demoMode = demoMode,
       _history = List<CommandLogEntry>.from(history);

  @override
  bool get connected => _connected;

  @override
  bool get demoMode => _demoMode;

  @override
  List<CommandLogEntry> get commandHistory => List<CommandLogEntry>.unmodifiable(_history);

  void setState({bool? connected, bool? demoMode, List<CommandLogEntry>? history}) {
    if (connected != null) {
      _connected = connected;
    }
    if (demoMode != null) {
      _demoMode = demoMode;
    }
    if (history != null) {
      _history = List<CommandLogEntry>.from(history);
    }
    notifyListeners();
  }

  @override
  void setJoystick(double x, double y) {
    lastJoystickX = x;
    lastJoystickY = y;
  }

  @override
  void releaseJoystick() {
    releaseCount += 1;
  }

  @override
  void clearCommandHistory() {
    clearCount += 1;
    _history = [];
    notifyListeners();
  }
}

class _FakeVideoPlayerPlatform extends VideoPlayerPlatform {
  int _nextId = 1;
  final Map<int, StreamController<VideoEvent>> _eventStreams =
      <int, StreamController<VideoEvent>>{};

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    final int id = _nextId++;
    late final StreamController<VideoEvent> controller;
    controller = StreamController<VideoEvent>.broadcast(
      onListen: () {
        controller.add(
          VideoEvent(
            eventType: VideoEventType.initialized,
            duration: const Duration(seconds: 10),
            size: const Size(1920, 1080),
          ),
        );
      },
    );
    _eventStreams[id] = controller;

    return id;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) {
    return _eventStreams[playerId]!.stream;
  }

  @override
  Widget buildView(int playerId) {
    return const SizedBox.shrink();
  }

  @override
  Future<void> setLooping(int playerId, bool looping) async {}

  @override
  Future<void> play(int playerId) async {}

  @override
  Future<void> pause(int playerId) async {}

  @override
  Future<void> setVolume(int playerId, double volume) async {}

  @override
  Future<void> seekTo(int playerId, Duration position) async {}

  @override
  Future<void> setPlaybackSpeed(int playerId, double speed) async {}

  @override
  Future<Duration> getPosition(int playerId) async => Duration.zero;

  @override
  Future<void> dispose(int playerId) async {
    await _eventStreams.remove(playerId)?.close();
  }
}

Future<void> _pumpCameraScreen(
  WidgetTester tester,
  _FakeBackendController controller,
) async {
  tester.view.physicalSize = const Size(1200, 2200);
  tester.view.devicePixelRatio = 1.0;

  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  await tester.pumpWidget(
    MaterialApp(
      home: CameraScreen(controller: controller),
    ),
  );
}

CommandLogEntry _sampleEntry() {
  return CommandLogEntry(
    key: 'cmd_vel',
    timestamp: DateTime(2026, 1, 1, 12, 0, 0),
    title: 'Joystick',
    details: '/cmd_vel command',
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late VideoPlayerPlatform originalVideoPlatform;

  setUpAll(() {
    originalVideoPlatform = VideoPlayerPlatform.instance;
    VideoPlayerPlatform.instance = _FakeVideoPlayerPlatform();
  });

  tearDownAll(() {
    VideoPlayerPlatform.instance = originalVideoPlatform;
  });

  testWidgets('shows offline info when disconnected and not in demo mode', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpCameraScreen(tester, controller);
    await tester.pump();

    expect(find.text('Camera Offline'), findsOneWidget);
    expect(find.text('Connect first'), findsOneWidget);
    expect(find.byType(CommandLogPanel), findsNothing);
  });

  testWidgets('hides offline info when backend is connected', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController(connected: true);

    await _pumpCameraScreen(tester, controller);
    await tester.pump();

    expect(find.text('Camera Offline'), findsNothing);
    expect(find.text('Connect first'), findsNothing);
    expect(find.byType(CommandLogPanel), findsNothing);
  });

  testWidgets('shows demo panel and video content in demo mode', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController(demoMode: true);

    await _pumpCameraScreen(tester, controller);

    expect(find.text('Demo camera feed'), findsOneWidget);

    await tester.pumpAndSettle();

    expect(find.byType(VideoPlayer), findsOneWidget);
    expect(find.byType(CommandLogPanel), findsOneWidget);
    expect(find.text('Wysłane komendy'), findsOneWidget);
    expect(find.text('Brak komend do pokazania.'), findsOneWidget);
  });

  testWidgets('clear button clears command history in demo mode', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController(
      demoMode: true,
      history: <CommandLogEntry>[_sampleEntry()],
    );

    await _pumpCameraScreen(tester, controller);
    await tester.pumpAndSettle();

    expect(find.text('Wyczyść'), findsOneWidget);
    expect(controller.clearCount, 0);

    await tester.tap(find.text('Wyczyść'));
    await tester.pumpAndSettle();

    expect(controller.clearCount, 1);
    expect(find.text('Brak komend do pokazania.'), findsOneWidget);
  });

  testWidgets('camera tabs switch selected button', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpCameraScreen(tester, controller);
    await tester.pump();

    expect(
      find.descendant(
        of: find.byType(FilledButton),
        matching: find.text('1'),
      ),
      findsOneWidget,
    );

    await tester.tap(find.text('2'));
    await tester.pumpAndSettle();

    expect(
      find.descendant(
        of: find.byType(FilledButton),
        matching: find.text('2'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byType(FilledButton),
        matching: find.text('1'),
      ),
      findsNothing,
    );
  });

  testWidgets('joystick callbacks are forwarded to backend controller', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpCameraScreen(tester, controller);
    await tester.pump();

    final RovJoystick joystick = tester.widget<RovJoystick>(find.byType(RovJoystick));

    expect(joystick.enabled, isTrue);

    joystick.onChanged(0.4, -0.6);
    joystick.onReleased();

    expect(controller.lastJoystickX, 0.4);
    expect(controller.lastJoystickY, -0.6);
    expect(controller.releaseCount, 1);
  });
}

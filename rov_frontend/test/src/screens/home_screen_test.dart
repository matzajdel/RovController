import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rov_frontend/src/backend_controller.dart';
import 'package:rov_frontend/src/screens/home_screen.dart';
import 'package:rov_frontend/src/widgets/command_log_panel.dart';

class _FakeBackendController extends BackendController {
  bool _connected;
  bool _demoMode;
  bool _backendStarted;
  List<CommandLogEntry> _history;

  int toggleDemoCount = 0;
  int disconnectCount = 0;
  int clearCount = 0;
  int emergencyStopCount = 0;

  double? lastJoystickX;
  double? lastJoystickY;
  int releaseCount = 0;

  _FakeBackendController({
    bool connected = false,
    bool demoMode = false,
    bool backendStarted = false,
    List<CommandLogEntry> history = const [],
  }) : _connected = connected,
       _demoMode = demoMode,
       _backendStarted = backendStarted,
       _history = List<CommandLogEntry>.from(history);

  @override
  bool get connected => _connected;

  @override
  bool get demoMode => _demoMode;

  @override
  bool get backendStarted => _backendStarted;

  @override
  bool get controlEnabled => _demoMode || _connected;

  @override
  List<CommandLogEntry> get commandHistory => List<CommandLogEntry>.unmodifiable(_history);

  void setState({
    bool? connected,
    bool? demoMode,
    bool? backendStarted,
    List<CommandLogEntry>? history,
  }) {
    if (connected != null) {
      _connected = connected;
    }
    if (demoMode != null) {
      _demoMode = demoMode;
    }
    if (backendStarted != null) {
      _backendStarted = backendStarted;
    }
    if (history != null) {
      _history = List<CommandLogEntry>.from(history);
    }
    notifyListeners();
  }

  @override
  void toggleDemoMode() {
    toggleDemoCount += 1;
    _demoMode = !_demoMode;
    notifyListeners();
  }

  @override
  void disconnect() {
    disconnectCount += 1;
    _connected = false;
    notifyListeners();
  }

  @override
  void clearCommandHistory() {
    clearCount += 1;
    _history = [];
    notifyListeners();
  }

  @override
  void emergencyStop() {
    emergencyStopCount += 1;
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
}

Future<void> _pumpHomeScreen(
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
      routes: <String, WidgetBuilder>{
        '/': (_) => HomeScreen(controller: controller),
        '/camera': (_) => const Scaffold(body: Text('CameraRouteScreen')),
      },
    ),
  );

  await tester.pump(const Duration(milliseconds: 100));
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

  testWidgets('shows disconnected status and connect action by default', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpHomeScreen(tester, controller);

    expect(find.text('Rozłączono'), findsOneWidget);
    expect(find.text('Połącz'), findsOneWidget);
    expect(find.text('Demo off'), findsOneWidget);

    final Finder emergencyStopButton = find.widgetWithText(FilledButton, 'Emergency Stop');
    final FilledButton button = tester.widget<FilledButton>(emergencyStopButton);
    expect(button.onPressed, isNull);
  });

  testWidgets('shows connected status and disconnect action when connected', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController(connected: true);

    await _pumpHomeScreen(tester, controller);

    expect(find.text('Połączono z ROSBridge'), findsOneWidget);
    expect(find.text('Rozłącz'), findsOneWidget);
    expect(find.text('Połącz'), findsNothing);

    await tester.tap(find.text('Rozłącz'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(controller.disconnectCount, 1);
    expect(find.text('Rozłączono'), findsOneWidget);
  });

  testWidgets('toggles demo mode and shows command log panel', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController(
      history: <CommandLogEntry>[_sampleEntry()],
    );

    await _pumpHomeScreen(tester, controller);

    expect(find.byType(CommandLogPanel), findsNothing);

    await tester.tap(find.text('Demo off'));
    await tester.pump(const Duration(milliseconds: 100));

    expect(controller.toggleDemoCount, 1);
    expect(find.text('Demo'), findsOneWidget);
    expect(find.text('Demo on'), findsOneWidget);
    expect(find.byType(CommandLogPanel), findsOneWidget);
    expect(find.text('Wysłane komendy'), findsOneWidget);

    await tester.tap(find.text('Wyczyść'));
    await tester.pump(const Duration(milliseconds: 100));

    expect(controller.clearCount, 1);
    expect(find.text('Brak komend do pokazania.'), findsOneWidget);
  });

  testWidgets('switches between Drive, Manipulator and Power screens', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpHomeScreen(tester, controller);

    expect(find.text('Drive'), findsOneWidget);

    await tester.tap(find.byTooltip('Next screen'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Manipulator'), findsOneWidget);

    await tester.tap(find.byTooltip('Next screen'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Power'), findsOneWidget);

    await tester.tap(find.byTooltip('Previous screen'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Manipulator'), findsOneWidget);
  });

  testWidgets('opens camera route from drive control grid', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpHomeScreen(tester, controller);

    await tester.tap(find.text('Camera'));
    await tester.pumpAndSettle(const Duration(milliseconds: 200));

    expect(find.text('CameraRouteScreen'), findsOneWidget);
  });

  testWidgets('emergency stop button calls controller when backend started', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController(backendStarted: true);

    await _pumpHomeScreen(tester, controller);

    final Finder emergencyStopButton = find.widgetWithText(FilledButton, 'Emergency Stop');
    final FilledButton button = tester.widget<FilledButton>(emergencyStopButton);
    expect(button.onPressed, isNotNull);

    await tester.tap(emergencyStopButton);
    await tester.pump(const Duration(milliseconds: 50));

    expect(controller.emergencyStopCount, 1);
  });
}

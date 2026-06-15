import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rov_frontend/src/backend_controller.dart';
import 'package:rov_frontend/src/screens/power_screen.dart';
import 'package:rov_frontend/src/widgets/command_log_panel.dart';

class _FakeBackendController extends BackendController {
  bool _demoMode;
  List<CommandLogEntry> _history;

  final List<String> publishedPowerMessages = <String>[];
  int clearCount = 0;

  _FakeBackendController({
    bool demoMode = false,
    List<CommandLogEntry> history = const <CommandLogEntry>[],
  }) : _demoMode = demoMode,
       _history = List<CommandLogEntry>.from(history);

  @override
  bool get demoMode => _demoMode;

  @override
  List<CommandLogEntry> get commandHistory => List<CommandLogEntry>.unmodifiable(_history);

  void setDemoModeValue(bool value) {
    _demoMode = value;
    notifyListeners();
  }

  @override
  void publishPowerCircuit(String message) {
    publishedPowerMessages.add(message);
  }

  @override
  void clearCommandHistory() {
    clearCount += 1;
    _history = <CommandLogEntry>[];
    notifyListeners();
  }
}

Future<void> _pumpPowerScreen(
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
      home: Scaffold(
        body: PowerScreen(controller: controller),
      ),
    ),
  );

  await tester.pump(const Duration(milliseconds: 50));
}

CommandLogEntry _sampleEntry() {
  return CommandLogEntry(
    key: 'powerbox',
    timestamp: DateTime(2026, 1, 1, 12, 0, 0),
    title: 'Powerbox',
    details: '/string_topic C1-ON',
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('renders header, counters and all 12 circuits', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpPowerScreen(tester, controller);

    expect(find.text('Zarządzanie obwodami'), findsOneWidget);
    expect(find.text('0 / 12 aktywnych'), findsOneWidget);
    expect(find.text('C1'), findsOneWidget);
    expect(find.text('ROS topic: /string_topic  |  type: std_msgs/msg/String  |  format: CX-ON / CX-OFF'), findsOneWidget);
  });

  testWidgets('tapping single circuit publishes ON and updates UI', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpPowerScreen(tester, controller);

    await tester.tap(find.text('C1'));
    await tester.pump();

    expect(controller.publishedPowerMessages, <String>['C1-ON']);

    await tester.pump(const Duration(milliseconds: 170));

    expect(find.text('1 / 12 aktywnych'), findsOneWidget);
    expect(find.text('Wysłano: C1-ON → /string_topic'), findsOneWidget);
  });

  testWidgets('pending state prevents duplicate tap publish for same circuit', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpPowerScreen(tester, controller);

    await tester.tap(find.text('C1'));
    await tester.pump();
    await tester.tap(find.text('C1'));
    await tester.pump();

    expect(controller.publishedPowerMessages, <String>['C1-ON']);

    await tester.pump(const Duration(milliseconds: 170));

    expect(find.text('1 / 12 aktywnych'), findsOneWidget);
  });

  testWidgets('all ON publishes 12 messages and all OFF publishes 12 OFF messages', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpPowerScreen(tester, controller);

    await tester.tap(find.text('ZAŁ'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 380));

    expect(controller.publishedPowerMessages.length, 12);
    expect(controller.publishedPowerMessages.first, 'C1-ON');
    expect(controller.publishedPowerMessages.last, 'C12-ON');
    expect(find.text('12 / 12 aktywnych'), findsOneWidget);
    expect(find.text('Wysłano: ALL-ON → /string_topic'), findsOneWidget);

    final Finder allOnButtonFinder = find.widgetWithText(FilledButton, 'ZAŁ');
    final FilledButton allOnButton = tester.widget<FilledButton>(allOnButtonFinder);
    expect(allOnButton.onPressed, isNull);

    await tester.tap(find.text('WYŁ'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 380));

    expect(controller.publishedPowerMessages.length, 24);
    expect(controller.publishedPowerMessages[12], 'C1-OFF');
    expect(controller.publishedPowerMessages.last, 'C12-OFF');
    expect(find.text('0 / 12 aktywnych'), findsOneWidget);
    expect(find.text('Wysłano: ALL-OFF → /string_topic'), findsOneWidget);
  });

  testWidgets('demo mode shows command log and clear action works', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController(
      demoMode: true,
      history: <CommandLogEntry>[_sampleEntry()],
    );

    await _pumpPowerScreen(tester, controller);

    expect(find.byType(CommandLogPanel), findsOneWidget);
    expect(find.text('Wysłane komendy'), findsOneWidget);

    await tester.tap(find.text('Wyczyść'));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));

    expect(controller.clearCount, 1);
  });
}

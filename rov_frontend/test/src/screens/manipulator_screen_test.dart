import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rov_frontend/src/backend_controller.dart';
import 'package:rov_frontend/src/screens/manipulator_screen.dart';
import 'package:rov_frontend/src/widgets/rov_joystick.dart';

class _FakeBackendController extends BackendController {
  final List<List<double>> publishedArrays = <List<double>>[];

  @override
  void publishManipulatorArray(List<double> values) {
    publishedArrays.add(List<double>.from(values));
  }
}

Future<void> _pumpManipulatorScreen(
  WidgetTester tester,
  _FakeBackendController controller, {
  required bool enabled,
}) async {
  tester.view.physicalSize = const Size(1200, 2200);
  tester.view.devicePixelRatio = 1.0;

  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ManipulatorScreen(
          enabled: enabled,
          controller: controller,
        ),
      ),
    ),
  );
}

Finder _springGestureFinder() {
  final Finder springPaint = find.byWidgetPredicate(
    (Widget widget) =>
        widget is CustomPaint &&
        widget.painter != null &&
        widget.painter.runtimeType.toString() == '_SpringGripPainter',
  );

  return find.ancestor(
    of: springPaint,
    matching: find.byType(GestureDetector),
  ).first;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('renders manipulator controls and labels', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpManipulatorScreen(tester, controller, enabled: true);
    await tester.pump();

    expect(find.text('Axis 5'), findsOneWidget);
    expect(find.text('Axis 6'), findsOneWidget);
    expect(find.text('Manipulator Model'), findsOneWidget);
    expect(find.text('A1 Base / A2 Shoulder'), findsOneWidget);
    expect(find.text('A3 Elbow / A4 Wrist'), findsOneWidget);
    expect(find.byType(RovJoystick), findsNWidgets(2));
  });

  testWidgets('publishes neutral array every 50ms', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpManipulatorScreen(tester, controller, enabled: true);

    await tester.pump(const Duration(milliseconds: 49));
    expect(controller.publishedArrays, isEmpty);

    await tester.pump(const Duration(milliseconds: 2));

    expect(controller.publishedArrays.length, 1);
    expect(controller.publishedArrays.first, <double>[0, 0, 0, 0, 0, 0]);
  });

  testWidgets('maps left and right joystick values into published array', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpManipulatorScreen(tester, controller, enabled: true);
    await tester.pump(const Duration(milliseconds: 55));

    final List<RovJoystick> joysticks =
        tester.widgetList<RovJoystick>(find.byType(RovJoystick)).toList();

    joysticks[0].onChanged(0.25, -0.5);
    await tester.pump(const Duration(milliseconds: 55));

    expect(
      controller.publishedArrays.last,
      <double>[25.0, -50.0, 0.0, 0.0, 0.0, 0.0],
    );

    joysticks[1].onChanged(0.6, -0.2);
    await tester.pump(const Duration(milliseconds: 55));

    expect(
      controller.publishedArrays.last,
      <double>[25.0, -50.0, -20.0, 60.0, 0.0, 0.0],
    );

    joysticks[0].onReleased();
    joysticks[1].onReleased();
    await tester.pump(const Duration(milliseconds: 55));

    expect(controller.publishedArrays.last, <double>[0, 0, 0, 0, 0, 0]);
  });

  testWidgets('updates axis5 from slider and axis6 from spring grip', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpManipulatorScreen(tester, controller, enabled: true);
    await tester.pump(const Duration(milliseconds: 55));

    final Slider axis5Slider = tester.widget<Slider>(find.byType(Slider));
    axis5Slider.onChanged!(0.7);
    await tester.pump(const Duration(milliseconds: 55));

    expect(controller.publishedArrays.last[4], closeTo(70.0, 0.001));

    final GestureDetector springGesture =
        tester.widget<GestureDetector>(_springGestureFinder());

    springGesture.onPanStart!(
      DragStartDetails(localPosition: const Offset(20, 0)),
    );
    await tester.pump(const Duration(milliseconds: 55));

    expect(controller.publishedArrays.last[5], closeTo(100.0, 0.001));

    springGesture.onPanEnd!(DragEndDetails());
    await tester.pump(const Duration(milliseconds: 55));

    expect(controller.publishedArrays.last[5], 0.0);
  });

  testWidgets('disables controls when enabled is false', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpManipulatorScreen(tester, controller, enabled: false);
    await tester.pump();

    final List<RovJoystick> joysticks =
        tester.widgetList<RovJoystick>(find.byType(RovJoystick)).toList();
    expect(joysticks[0].enabled, isFalse);
    expect(joysticks[1].enabled, isFalse);

    final Slider axis5Slider = tester.widget<Slider>(find.byType(Slider));
    expect(axis5Slider.onChanged, isNull);

    final GestureDetector springGesture =
        tester.widget<GestureDetector>(_springGestureFinder());
    expect(springGesture.onPanStart, isNull);
    expect(springGesture.onPanUpdate, isNull);
    expect(springGesture.onPanEnd, isNull);
  });

  testWidgets('stops publish timer after widget dispose', (WidgetTester tester) async {
    final _FakeBackendController controller = _FakeBackendController();

    await _pumpManipulatorScreen(tester, controller, enabled: true);
    await tester.pump(const Duration(milliseconds: 120));

    final int beforeDisposeCount = controller.publishedArrays.length;
    expect(beforeDisposeCount, greaterThan(0));

    await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
    await tester.pump(const Duration(milliseconds: 200));

    expect(controller.publishedArrays.length, beforeDisposeCount);
  });
}

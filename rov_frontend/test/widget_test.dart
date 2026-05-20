// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:rov_frontend/main.dart';

void main() {
  testWidgets('App boots and shows connect UI', (WidgetTester tester) async {
    await tester.pumpWidget(const RovApp());

    expect(find.text('Disconnected'), findsOneWidget);
    expect(find.text('Connect'), findsOneWidget);
    // Ensure main CTA exists.
    expect(find.text('Emergency Stop'), findsOneWidget);
  });
}

import 'package:divtrack/core/widgets/disclaimer_strip.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('DisclaimerStrip shows the default educational text', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: DisclaimerStrip())),
    );
    expect(find.textContaining('geen financieel'), findsOneWidget);
    expect(find.byIcon(Icons.info_outline), findsOneWidget);
  });

  testWidgets('DisclaimerStrip renders custom text', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: DisclaimerStrip(text: 'Eigen disclaimer')),
      ),
    );
    expect(find.text('Eigen disclaimer'), findsOneWidget);
  });
}

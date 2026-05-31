import 'package:divtrack/core/utils/formatters.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

void main() {
  setUpAll(() async {
    await initializeDateFormatting('nl_BE');
  });

  group('Money', () {
    test('formats EUR with the euro symbol', () {
      final out = Money.format(1234.5, currency: 'EUR');
      expect(out.contains('€'), isTrue);
    });

    test('formats USD with the dollar symbol', () {
      final out = Money.format(10, currency: 'USD');
      expect(out.contains('\$'), isTrue);
    });
  });

  group('Percent', () {
    test('adds a leading + when signed and positive', () {
      expect(Percent.format(0.15, signed: true).startsWith('+'), isTrue);
    });

    test('does not add + for negative values', () {
      expect(Percent.format(-0.15, signed: true).startsWith('+'), isFalse);
    });
  });
}

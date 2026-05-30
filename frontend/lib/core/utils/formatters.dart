import 'package:intl/intl.dart';

/// Locale-aware money and percentage formatting (default nl-BE / EUR).
class Money {
  const Money._();

  static String format(num value, {String currency = 'EUR', String locale = 'nl_BE'}) {
    final fmt = NumberFormat.currency(
      locale: locale,
      symbol: _symbol(currency),
      decimalDigits: 2,
    );
    return fmt.format(value);
  }

  static String compact(num value, {String currency = 'EUR', String locale = 'nl_BE'}) {
    final fmt = NumberFormat.compactCurrency(
      locale: locale,
      symbol: _symbol(currency),
    );
    return fmt.format(value);
  }

  static String _symbol(String currency) {
    switch (currency.toUpperCase()) {
      case 'EUR':
        return '€';
      case 'USD':
        return '\$';
      case 'GBP':
        return '£';
      default:
        return '$currency ';
    }
  }
}

class Percent {
  const Percent._();

  /// [value] is a fraction (0.15 => "15,0%"). Adds a leading sign when [signed].
  static String format(num value, {int decimals = 1, bool signed = false, String locale = 'nl_BE'}) {
    final fmt = NumberFormat.decimalPercentPattern(locale: locale, decimalDigits: decimals);
    final text = fmt.format(value);
    if (signed && value > 0) return '+$text';
    return text;
  }
}

String formatDate(DateTime date, {String locale = 'nl_BE'}) =>
    DateFormat.yMMMd(locale).format(date);

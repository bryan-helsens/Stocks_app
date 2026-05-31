import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';

/// A single dividend calendar event (confirmed or projected).
class CalendarEvent {
  const CalendarEvent({
    required this.date,
    required this.kind,
    required this.eventType,
    required this.ticker,
    required this.name,
    required this.currency,
    this.amount,
  });

  final DateTime date;
  final String kind; // CONFIRMED | PROJECTED
  final String eventType; // PAID | EX_DIVIDEND | PAY_DATE
  final String ticker;
  final String name;
  final String currency;
  final double? amount;

  bool get isProjected => kind == 'PROJECTED';

  factory CalendarEvent.fromJson(Map<String, dynamic> j) => CalendarEvent(
        date: DateTime.parse(j['date'] as String),
        kind: j['kind'] as String,
        eventType: j['event_type'] as String,
        ticker: j['ticker'] as String,
        name: j['name'] as String,
        currency: j['currency'] as String? ?? 'EUR',
        amount: j['amount'] == null ? null : double.tryParse(j['amount'].toString()),
      );
}

class CalendarRepository {
  CalendarRepository(this._client);
  final ApiClient _client;

  Future<List<CalendarEvent>> month(DateTime month, {bool includeProjected = true}) async {
    final start = DateTime(month.year, month.month, 1);
    final end = DateTime(month.year, month.month + 1, 0); // last day of month
    final res = await _client.raw.get('/dividends/calendar', queryParameters: {
      'start': _fmt(start),
      'end': _fmt(end),
      'include_projected': includeProjected,
    });
    final events = (res.data as Map<String, dynamic>)['events'] as List;
    return events.map((e) => CalendarEvent.fromJson(e as Map<String, dynamic>)).toList();
  }

  String _fmt(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}

final calendarRepositoryProvider =
    Provider<CalendarRepository>((ref) => CalendarRepository(ref.watch(apiClientProvider)));

/// Currently viewed month (first day).
final calendarMonthProvider =
    StateProvider<DateTime>((ref) => DateTime(DateTime.now().year, DateTime.now().month, 1));

/// Toggle for showing projected (estimated) events.
final includeProjectedProvider = StateProvider<bool>((ref) => true);

final calendarEventsProvider = FutureProvider<List<CalendarEvent>>((ref) async {
  final month = ref.watch(calendarMonthProvider);
  final projected = ref.watch(includeProjectedProvider);
  return ref.watch(calendarRepositoryProvider).month(month, includeProjected: projected);
});

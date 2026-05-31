import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/disclaimer_strip.dart';
import '../data/calendar_repository.dart';

/// Dividend calendar (M6): a month-navigable agenda of confirmed and projected
/// ex-dividend / pay-date events, with a toggle to hide estimates.
class CalendarPage extends ConsumerWidget {
  const CalendarPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final month = ref.watch(calendarMonthProvider);
    final projected = ref.watch(includeProjectedProvider);
    final events = ref.watch(calendarEventsProvider);

    return Column(
      children: [
        _MonthBar(month: month),
        SwitchListTile(
          dense: true,
          title: const Text('Toon verwachte dividenden'),
          value: projected,
          onChanged: (v) => ref.read(includeProjectedProvider.notifier).state = v,
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () async => ref.refresh(calendarEventsProvider.future),
            child: AsyncValueView<List<CalendarEvent>>(
              value: events,
              onRetry: () => ref.refresh(calendarEventsProvider),
              data: (list) => _EventList(events: list),
            ),
          ),
        ),
        const Padding(
          padding: EdgeInsets.all(12),
          child: DisclaimerStrip(text: 'Verwachte dividenden zijn schattingen, geen garanties.'),
        ),
      ],
    );
  }
}

class _MonthBar extends ConsumerWidget {
  const _MonthBar({required this.month});
  final DateTime month;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final label = DateFormat.yMMMM('nl_BE').format(month);
    void shift(int delta) => ref.read(calendarMonthProvider.notifier).state =
        DateTime(month.year, month.month + delta, 1);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(onPressed: () => shift(-1), icon: const Icon(Icons.chevron_left)),
          Text(label, style: Theme.of(context).textTheme.titleMedium),
          IconButton(onPressed: () => shift(1), icon: const Icon(Icons.chevron_right)),
        ],
      ),
    );
  }
}

class _EventList extends StatelessWidget {
  const _EventList({required this.events});
  final List<CalendarEvent> events;

  @override
  Widget build(BuildContext context) {
    if (events.isEmpty) {
      return ListView(children: const [
        SizedBox(height: 80),
        Center(child: Text('Geen dividend-events deze maand.')),
      ]);
    }
    // Group by day.
    final byDay = <int, List<CalendarEvent>>{};
    for (final e in events) {
      byDay.putIfAbsent(e.date.day, () => []).add(e);
    }
    final days = byDay.keys.toList()..sort();
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      children: [
        for (final d in days) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(4, 12, 4, 4),
            child: Text('${d.toString().padLeft(2, '0')} '
                '${DateFormat.MMMM('nl_BE').format(byDay[d]!.first.date)}',
                style: Theme.of(context).textTheme.labelLarge),
          ),
          for (final e in byDay[d]!) _EventTile(event: e),
        ],
      ],
    );
  }
}

class _EventTile extends StatelessWidget {
  const _EventTile({required this.event});
  final CalendarEvent event;

  @override
  Widget build(BuildContext context) {
    final (label, icon, color) = switch (event.eventType) {
      'EX_DIVIDEND' => ('Ex-dividend', Icons.event_busy, AppColors.warning),
      'PAY_DATE' => ('Verwachte betaling', Icons.schedule, AppColors.primary),
      _ => ('Ontvangen', Icons.check_circle, AppColors.positive),
    };
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 3),
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text('${event.ticker} · ${event.name}'),
        subtitle: Text('$label${event.isProjected ? ' (schatting)' : ''}'),
        trailing: event.amount != null
            ? Text(Money.format(event.amount!, currency: event.currency),
                style: const TextStyle(fontWeight: FontWeight.w600))
            : null,
      ),
    );
  }
}

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/disclaimer_strip.dart';

/// Dividend dashboard (M5): totals, per-year bars and yield/CAGR.
final dividendDashboardProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final res = await ref.watch(apiClientProvider).raw.get('/dividends/dashboard');
  return res.data as Map<String, dynamic>;
});

class DividendsPage extends ConsumerWidget {
  const DividendsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(dividendDashboardProvider);
    return RefreshIndicator(
      onRefresh: () async => ref.refresh(dividendDashboardProvider.future),
      child: AsyncValueView<Map<String, dynamic>>(
        value: data,
        onRetry: () => ref.refresh(dividendDashboardProvider),
        data: (d) {
          double n(Object? v) => double.tryParse('${v ?? 0}') ?? 0;
          final ccy = d['currency']?.toString() ?? 'EUR';
          final byYear = (d['by_year'] as Map?)?.cast<String, dynamic>() ?? {};
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Wrap(spacing: 12, runSpacing: 12, children: [
                _stat(context, 'Totaal ontvangen', Money.format(n(d['total_received']), currency: ccy)),
                _stat(context, 'Gem. per maand', Money.format(n(d['avg_monthly']), currency: ccy)),
                _stat(context, 'CAGR',
                    d['cagr'] == null ? 'n.b.' : Percent.format(n(d['cagr']))),
                _stat(context, 'Projectie 12m',
                    Money.format(n(d['projected_next_12m']), currency: ccy)),
              ]),
              const SizedBox(height: 16),
              if (byYear.isNotEmpty) _YearBars(byYear: byYear, currency: ccy),
              const SizedBox(height: 16),
              const DisclaimerStrip(
                text: 'Verwachte dividenden zijn schattingen, geen garanties.',
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _stat(BuildContext context, String label, String value) => SizedBox(
        width: 200,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 6),
                Text(value, style: Theme.of(context).textTheme.titleLarge),
              ],
            ),
          ),
        ),
      );
}

class _YearBars extends StatelessWidget {
  const _YearBars({required this.byYear, required this.currency});
  final Map<String, dynamic> byYear;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final years = byYear.keys.toList()..sort();
    final values = [for (final y in years) double.tryParse('${byYear[y]}') ?? 0];
    final maxY = (values.isEmpty ? 1.0 : values.reduce((a, b) => a > b ? a : b)) * 1.2;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Dividend per jaar', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 16),
            SizedBox(
              height: 200,
              child: BarChart(
                BarChartData(
                  maxY: maxY,
                  titlesData: FlTitlesData(
                    leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        getTitlesWidget: (v, _) {
                          final i = v.toInt();
                          if (i < 0 || i >= years.length) return const SizedBox.shrink();
                          return Text(years[i], style: const TextStyle(fontSize: 10));
                        },
                      ),
                    ),
                  ),
                  borderData: FlBorderData(show: false),
                  barGroups: [
                    for (var i = 0; i < values.length; i++)
                      BarChartGroupData(x: i, barRods: [
                        BarChartRodData(
                          toY: values[i],
                          color: Theme.of(context).colorScheme.primary,
                          width: 18,
                          borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
                        ),
                      ]),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

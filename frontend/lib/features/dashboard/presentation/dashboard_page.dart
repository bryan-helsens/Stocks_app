import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../portfolio/data/portfolio_models.dart';
import '../../portfolio/data/portfolio_repository.dart';

/// Portfolio dashboard (M7): headline KPIs, value and an asset-class allocation
/// donut. Empty state nudges the user to import or add transactions.
class DashboardPage extends ConsumerWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(portfolioSummaryProvider);
    return RefreshIndicator(
      onRefresh: () async => ref.refresh(portfolioSummaryProvider.future),
      child: AsyncValueView<PortfolioSummary?>(
        value: summary,
        onRetry: () => ref.refresh(portfolioSummaryProvider),
        data: (s) {
          if (s == null) return const _EmptyState();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _KpiRow(summary: s),
              const SizedBox(height: 16),
              _AllocationCard(summary: s),
            ],
          );
        },
      ),
    );
  }
}

class _KpiRow extends StatelessWidget {
  const _KpiRow({required this.summary});
  final PortfolioSummary summary;

  @override
  Widget build(BuildContext context) {
    final ccy = summary.baseCurrency;
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        _KpiCard(
          label: 'Totale waarde',
          value: Money.format(summary.totalValue, currency: ccy),
        ),
        _KpiCard(
          label: 'Onrealiseerde W/V',
          value: Money.format(summary.totalUnrealized, currency: ccy),
          delta: summary.unrealizedPct,
        ),
        _KpiCard(
          label: 'Geïnvesteerd',
          value: Money.format(summary.totalInvested, currency: ccy),
        ),
        _KpiCard(
          label: 'Gerealiseerd',
          value: Money.format(summary.realizedPnl, currency: ccy),
          delta: summary.realizedPnl == 0 ? null : (summary.realizedPnl > 0 ? 1 : -1),
        ),
      ],
    );
  }
}

class _KpiCard extends StatelessWidget {
  const _KpiCard({required this.label, required this.value, this.delta});
  final String label;
  final String value;
  final double? delta;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 220,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 6),
              Text(value, style: Theme.of(context).textTheme.titleLarge),
              if (delta != null)
                Text(
                  Percent.format(delta!, signed: true),
                  style: TextStyle(color: pnlColor(context, delta!)),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AllocationCard extends StatelessWidget {
  const _AllocationCard({required this.summary});
  final PortfolioSummary summary;

  @override
  Widget build(BuildContext context) {
    final byClass = <String, double>{};
    for (final h in summary.holdings) {
      final value = h.marketValue ?? h.totalInvested;
      byClass.update(h.asset.assetClass, (v) => v + value, ifAbsent: () => value);
    }
    final total = byClass.values.fold<double>(0, (a, b) => a + b);
    final entries = byClass.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final colors = _palette(context);

    if (total <= 0) {
      return const Card(
        child: Padding(padding: EdgeInsets.all(24), child: Text('Nog geen allocatiegegevens.')),
      );
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Asset allocatie', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 16),
            SizedBox(
              height: 200,
              child: Row(
                children: [
                  Expanded(
                    child: PieChart(
                      PieChartData(
                        sectionsSpace: 2,
                        centerSpaceRadius: 48,
                        sections: [
                          for (var i = 0; i < entries.length; i++)
                            PieChartSectionData(
                              value: entries[i].value,
                              color: colors[i % colors.length],
                              title: Percent.format(entries[i].value / total, decimals: 0),
                              radius: 56,
                              titleStyle: const TextStyle(
                                  fontSize: 11, color: Colors.white, fontWeight: FontWeight.bold),
                            ),
                        ],
                      ),
                    ),
                  ),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        for (var i = 0; i < entries.length; i++)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 3),
                            child: Row(
                              children: [
                                Container(width: 12, height: 12, color: colors[i % colors.length]),
                                const SizedBox(width: 8),
                                Text('${entries[i].key} · '
                                    '${Percent.format(entries[i].value / total, decimals: 0)}'),
                              ],
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Color> _palette(BuildContext context) => const [
        AppColors.primary,
        AppColors.positive,
        AppColors.warning,
        Color(0xFF8B5CF6),
        Color(0xFF06B6D4),
        Color(0xFFEC4899),
      ];
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 80),
        Icon(Icons.insights_outlined, size: 56, color: Theme.of(context).colorScheme.primary),
        const SizedBox(height: 16),
        Center(
          child: Text('Nog geen portefeuille', style: Theme.of(context).textTheme.titleLarge),
        ),
        const SizedBox(height: 8),
        const Center(child: Text('Importeer je BUX-bestand of voeg transacties toe.')),
      ],
    );
  }
}

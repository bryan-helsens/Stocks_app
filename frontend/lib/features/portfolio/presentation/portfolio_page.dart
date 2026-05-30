import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/async_value_view.dart';
import '../data/portfolio_models.dart';
import '../data/portfolio_repository.dart';

/// Holdings list (M2). Tapping a row could open a position detail (future).
class PortfolioPage extends ConsumerWidget {
  const PortfolioPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(portfolioSummaryProvider);
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.refresh(portfolioSummaryProvider.future),
        child: AsyncValueView<PortfolioSummary?>(
          value: summary,
          onRetry: () => ref.refresh(portfolioSummaryProvider),
          data: (s) {
            if (s == null || s.holdings.isEmpty) {
              return ListView(children: const [
                SizedBox(height: 120),
                Center(child: Text('Geen posities. Importeer of voeg een transactie toe.')),
              ]);
            }
            return ListView.separated(
              padding: const EdgeInsets.all(12),
              itemCount: s.holdings.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (_, i) => _HoldingTile(holding: s.holdings[i], currency: s.baseCurrency),
            );
          },
        ),
      ),
    );
  }
}

class _HoldingTile extends StatelessWidget {
  const _HoldingTile({required this.holding, required this.currency});
  final Holding holding;
  final String currency;

  static String _initials(String ticker) =>
      ticker.length <= 2 ? ticker : ticker.substring(0, 2);

  @override
  Widget build(BuildContext context) {
    final upl = holding.unrealizedPnl ?? 0;
    final pct = holding.unrealizedPct ?? 0;
    return ListTile(
      leading: CircleAvatar(child: Text(_initials(holding.asset.ticker))),
      title: Text(holding.asset.ticker,
          style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: Text('${holding.asset.name} · ${holding.quantity.toStringAsFixed(2)} @ '
          '${Money.format(holding.avgCost, currency: currency)}'),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(holding.marketValue != null
              ? Money.format(holding.marketValue!, currency: currency)
              : 'n.b.'),
          if (holding.unrealizedPnl != null)
            Text(
              '${Money.format(upl, currency: currency)} (${Percent.format(pct, signed: true)})',
              style: TextStyle(fontSize: 12, color: pnlColor(context, upl)),
            ),
        ],
      ),
    );
  }
}

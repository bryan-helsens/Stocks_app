import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../transactions/presentation/add_transaction_sheet.dart';
import '../data/portfolio_models.dart';
import '../data/portfolio_repository.dart';
import 'position_detail_page.dart';

/// Holdings list (M2). Tap a row for the position detail; the FAB adds a manual
/// transaction (with asset search).
class PortfolioPage extends ConsumerWidget {
  const PortfolioPage({super.key});

  Future<void> _addTransaction(BuildContext context, WidgetRef ref) async {
    final portfolios = await ref.read(portfoliosProvider.future);
    if (portfolios.isEmpty) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Maak eerst een portefeuille aan.')),
        );
      }
      return;
    }
    final selected = ref.read(selectedPortfolioProvider) ?? portfolios.first.id;
    if (context.mounted) await AddTransactionSheet.show(context, selected);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(portfolioSummaryProvider);
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _addTransaction(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Transactie'),
      ),
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
      onTap: holding.asset.id == null
          ? null
          : () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => PositionDetailPage(holding: holding, currency: currency),
                ),
              ),
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

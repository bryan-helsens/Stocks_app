import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/disclaimer_strip.dart';
import '../../analysis/data/analysis_repository.dart';
import '../data/portfolio_models.dart';

/// Position detail (M2/M8/M9): overview, quality score and an on-demand
/// valuation (DCF/DDM/multiples). Educational only.
class PositionDetailPage extends ConsumerStatefulWidget {
  const PositionDetailPage({super.key, required this.holding, required this.currency});

  final Holding holding;
  final String currency;

  @override
  ConsumerState<PositionDetailPage> createState() => _PositionDetailPageState();
}

class _PositionDetailPageState extends ConsumerState<PositionDetailPage> {
  List<ValuationItem>? _valuations;
  bool _valuating = false;
  String? _valError;

  // Minimal DDM inputs (the user can refine; defaults are conservative).
  final _dps = TextEditingController(text: '1.0');
  final _divGrowth = TextEditingController(text: '0.05');
  final _reqReturn = TextEditingController(text: '0.09');

  @override
  void dispose() {
    _dps.dispose();
    _divGrowth.dispose();
    _reqReturn.dispose();
    super.dispose();
  }

  Future<void> _runValuation() async {
    final assetId = widget.holding.asset.id;
    if (assetId == null) return;
    setState(() {
      _valuating = true;
      _valError = null;
    });
    try {
      final items = await ref.read(analysisRepositoryProvider).valuation(assetId, {
        if (widget.holding.price != null) 'current_price': widget.holding.price.toString(),
        'dividend_per_share': _dps.text,
        'dividend_growth': _divGrowth.text,
        'required_return': _reqReturn.text,
      });
      setState(() => _valuations = items);
    } on ApiException catch (e) {
      setState(() => _valError = e.message);
    } finally {
      if (mounted) setState(() => _valuating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final h = widget.holding;
    final ccy = widget.currency;
    final assetId = h.asset.id;
    return Scaffold(
      appBar: AppBar(title: Text('${h.asset.ticker} · ${h.asset.name}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _overviewCard(context, h, ccy),
          const SizedBox(height: 16),
          if (assetId != null) _scoreSection(assetId),
          const SizedBox(height: 16),
          _valuationSection(context),
          const SizedBox(height: 16),
          const DisclaimerStrip(),
        ],
      ),
    );
  }

  Widget _overviewCard(BuildContext context, Holding h, String ccy) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Overzicht', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              _row('Aantal', h.quantity.toStringAsFixed(4)),
              _row('Gem. kostprijs', Money.format(h.avgCost, currency: ccy)),
              _row('Geïnvesteerd', Money.format(h.totalInvested, currency: ccy)),
              if (h.price != null) _row('Koers', Money.format(h.price!, currency: ccy)),
              if (h.marketValue != null) _row('Marktwaarde', Money.format(h.marketValue!, currency: ccy)),
              if (h.unrealizedPnl != null)
                _row('Onrealiseerde W/V', Money.format(h.unrealizedPnl!, currency: ccy)),
              _row('Gerealiseerde W/V', Money.format(h.realizedPnl, currency: ccy)),
            ],
          ),
        ),
      );

  Widget _scoreSection(String assetId) {
    final score = ref.watch(assetScoreProvider(assetId));
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: AsyncValueView<AssetScore>(
          value: score,
          onRetry: () => ref.refresh(assetScoreProvider(assetId)),
          data: (s) {
            if (!s.hasFundamentals) {
              return const Text('Geen fundamentele data beschikbaar voor een score.');
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('Kwaliteitsscore', style: Theme.of(context).textTheme.titleMedium),
                    const Spacer(),
                    Text('${s.total?.toStringAsFixed(0) ?? '-'}/100',
                        style: Theme.of(context).textTheme.titleLarge),
                  ],
                ),
                const SizedBox(height: 8),
                _bar('Waardering', s.valuation),
                _bar('Groei', s.growth),
                _bar('Gezondheid', s.health),
                _bar('Dividend', s.dividend),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _valuationSection(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Waardering (DDM)', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: _field(_dps, 'Dividend/aandeel')),
                const SizedBox(width: 8),
                Expanded(child: _field(_divGrowth, 'Groei')),
                const SizedBox(width: 8),
                Expanded(child: _field(_reqReturn, 'Vereist rend.')),
              ]),
              const SizedBox(height: 8),
              FilledButton(
                onPressed: _valuating ? null : _runValuation,
                child: _valuating
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Bereken fair value'),
              ),
              if (_valError != null) Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_valError!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
              if (_valuations != null) ...[
                const SizedBox(height: 12),
                for (final v in _valuations!)
                  ListTile(
                    dense: true,
                    title: Text(v.method),
                    subtitle: Text(v.fairValue != null
                        ? 'Fair value ${Money.format(v.fairValue!, currency: widget.currency)} · '
                            'MoS ${v.marginOfSafety != null ? Percent.format(v.marginOfSafety!, signed: true) : 'n.b.'}'
                        : 'Onvoldoende betrouwbaar'),
                    trailing: _verdictChip(v.verdict),
                  ),
              ],
            ],
          ),
        ),
      );

  Widget _verdictChip(String verdict) {
    final (label, color) = switch (verdict) {
      'UNDERVALUED' => ('Ondergewaardeerd', Colors.green),
      'OVERVALUED' => ('Overgewaardeerd', Colors.red),
      _ => ('Correct', Colors.blueGrey),
    };
    return Chip(label: Text(label), backgroundColor: color.withValues(alpha: 0.15));
  }

  Widget _bar(String label, double? value) {
    final v = (value ?? 0) / 100;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(width: 96, child: Text(label)),
          Expanded(
            child: LinearProgressIndicator(value: v.clamp(0, 1), minHeight: 8),
          ),
          const SizedBox(width: 8),
          SizedBox(width: 32, child: Text(value?.toStringAsFixed(0) ?? '-')),
        ],
      ),
    );
  }

  Widget _field(TextEditingController c, String label) => TextField(
        controller: c,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(labelText: label, isDense: true),
      );

  Widget _row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [Text(label), Text(value, style: const TextStyle(fontWeight: FontWeight.w600))],
        ),
      );
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/disclaimer_strip.dart';

/// Belgian tax overview (M17) — informational only. Fetches the per-year
/// aggregation (dividends, RV, foreign withholding, TOB, fees).
class TaxPage extends ConsumerStatefulWidget {
  const TaxPage({super.key});

  @override
  ConsumerState<TaxPage> createState() => _TaxPageState();
}

class _TaxPageState extends ConsumerState<TaxPage> {
  int _year = DateTime.now().year - 1;
  Map<String, dynamic>? _data;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await ref.read(apiClientProvider).raw.get(
        '/tax/be/report',
        queryParameters: {'year': _year},
      );
      setState(() => _data = res.data as Map<String, dynamic>);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    double n(Object? v) => double.tryParse('${v ?? 0}') ?? 0;
    final d = _data;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            const Text('Jaar:'),
            const SizedBox(width: 12),
            DropdownButton<int>(
              value: _year,
              items: [
                for (var y = DateTime.now().year; y >= DateTime.now().year - 6; y--)
                  DropdownMenuItem(value: y, child: Text('$y')),
              ],
              onChanged: (v) {
                if (v != null) {
                  setState(() => _year = v);
                  _load();
                }
              },
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (_busy) const Center(child: Padding(padding: EdgeInsets.all(32), child: CircularProgressIndicator())),
        if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        if (d != null) ...[
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _row('Buitenlandse dividenden (bruto)', Money.format(n(d['foreign_dividends_gross']))),
                  _row('Belgische dividenden (bruto)', Money.format(n(d['belgian_dividends_gross']))),
                  _row('Buitenlandse bronbelasting', Money.format(n(d['withholding_tax_foreign']))),
                  _row('Roerende voorheffing (30%)', Money.format(n(d['belgian_rv']))),
                  _row('Beurstaks (TOB)', Money.format(n(d['tob_total']))),
                  _row('Transactiekosten', Money.format(n(d['fees_total']))),
                  const Divider(),
                  _row('Netto dividendinkomen', Money.format(n(d['net_dividend_income'])), bold: true),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          DisclaimerStrip(text: d['disclaimer']?.toString() ?? DisclaimerStrip.defaultText),
        ],
      ],
    );
  }

  Widget _row(String label, String value, {bool bold = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label),
            Text(value,
                style: TextStyle(fontWeight: bold ? FontWeight.bold : FontWeight.normal)),
          ],
        ),
      );
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../portfolio/data/portfolio_models.dart';
import '../../portfolio/data/portfolio_repository.dart';

/// Bottom sheet to add a manual transaction (M3) with live asset search (M4).
/// Returns true when a transaction was saved so the caller can refresh.
class AddTransactionSheet extends ConsumerStatefulWidget {
  const AddTransactionSheet({super.key, required this.portfolioId});

  final String portfolioId;

  static Future<bool?> show(BuildContext context, String portfolioId) =>
      showModalBottomSheet<bool>(
        context: context,
        isScrollControlled: true,
        builder: (_) => Padding(
          padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
          child: AddTransactionSheet(portfolioId: portfolioId),
        ),
      );

  @override
  ConsumerState<AddTransactionSheet> createState() => _AddTransactionSheetState();
}

class _AddTransactionSheetState extends ConsumerState<AddTransactionSheet> {
  String _type = 'BUY';
  AssetRef? _asset;
  final _search = TextEditingController();
  final _quantity = TextEditingController();
  final _price = TextEditingController();
  final _amount = TextEditingController();
  List<AssetRef> _results = [];
  bool _searching = false;
  bool _busy = false;
  String? _error;

  bool get _needsAsset => _type == 'BUY' || _type == 'SELL' || _type == 'DIVIDEND';
  bool get _needsQtyPrice => _type == 'BUY' || _type == 'SELL';

  @override
  void dispose() {
    _search.dispose();
    _quantity.dispose();
    _price.dispose();
    _amount.dispose();
    super.dispose();
  }

  Future<void> _doSearch(String q) async {
    if (q.trim().isEmpty) {
      setState(() => _results = []);
      return;
    }
    setState(() => _searching = true);
    try {
      final res = await ref.read(apiClientProvider).raw.get(
        '/market/search',
        queryParameters: {'q': q},
      );
      setState(() => _results =
          (res.data as List).map((e) => AssetRef.fromJson(e as Map<String, dynamic>)).toList());
    } catch (_) {
      setState(() => _results = []);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final body = <String, dynamic>{
        'portfolio_id': widget.portfolioId,
        'type': _type,
        'trade_date': DateTime.now().toUtc().toIso8601String(),
        'currency': _asset?.currency ?? 'EUR',
        if (_needsAsset) 'asset_id': _asset?.id,
        if (_needsQtyPrice) 'quantity': _quantity.text,
        if (_needsQtyPrice) 'price': _price.text,
        if (!_needsQtyPrice && _amount.text.isNotEmpty) 'gross_amount': _amount.text,
      };
      if (_needsAsset && _asset?.id == null) {
        setState(() => _error = 'Kies een asset uit de zoekresultaten.');
        return;
      }
      await ref.read(portfolioRepositoryProvider).addTransaction(body);
      ref.invalidate(portfolioSummaryProvider);
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Transactie toevoegen', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _type,
            decoration: const InputDecoration(labelText: 'Type'),
            items: const [
              DropdownMenuItem(value: 'BUY', child: Text('Koop')),
              DropdownMenuItem(value: 'SELL', child: Text('Verkoop')),
              DropdownMenuItem(value: 'DIVIDEND', child: Text('Dividend')),
              DropdownMenuItem(value: 'DEPOSIT', child: Text('Storting')),
              DropdownMenuItem(value: 'WITHDRAWAL', child: Text('Opname')),
            ],
            onChanged: (v) => setState(() => _type = v ?? 'BUY'),
          ),
          if (_needsAsset) ...[
            const SizedBox(height: 12),
            TextField(
              controller: _search,
              decoration: InputDecoration(
                labelText: _asset == null ? 'Zoek asset (ticker/naam)' : 'Asset: ${_asset!.ticker}',
                suffixIcon: _searching
                    ? const Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2)))
                    : const Icon(Icons.search),
              ),
              onChanged: _doSearch,
            ),
            if (_results.isNotEmpty)
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 160),
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    for (final a in _results)
                      ListTile(
                        dense: true,
                        title: Text('${a.ticker} · ${a.name}'),
                        subtitle: Text('${a.assetClass}${a.id == null ? ' (nieuw)' : ''}'),
                        onTap: () => setState(() {
                          _asset = a;
                          _results = [];
                          _search.text = a.ticker;
                        }),
                      ),
                  ],
                ),
              ),
          ],
          if (_needsQtyPrice) ...[
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: _num(_quantity, 'Aantal')),
              const SizedBox(width: 12),
              Expanded(child: _num(_price, 'Prijs')),
            ]),
          ] else ...[
            const SizedBox(height: 12),
            _num(_amount, 'Bedrag'),
          ],
          if (_error != null) Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: _busy
                ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Opslaan'),
          ),
        ],
      ),
    );
  }

  Widget _num(TextEditingController c, String label) => TextField(
        controller: c,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(labelText: label),
      );
}

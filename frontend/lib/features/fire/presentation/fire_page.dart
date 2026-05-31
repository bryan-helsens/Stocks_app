import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/disclaimer_strip.dart';

/// FIRE planner (M10): inputs → Lean/Coast/Barista/Fat targets + FI date.
class FirePage extends ConsumerStatefulWidget {
  const FirePage({super.key});

  @override
  ConsumerState<FirePage> createState() => _FirePageState();
}

class _FirePageState extends ConsumerState<FirePage> {
  final _expenses = TextEditingController(text: '30000');
  final _swr = TextEditingController(text: '0.04');
  final _current = TextEditingController(text: '50000');
  final _monthly = TextEditingController(text: '800');
  final _return = TextEditingController(text: '0.07');

  Map<String, dynamic>? _result;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    for (final c in [_expenses, _swr, _current, _monthly, _return]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _compute() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await ref.read(apiClientProvider).raw.post('/fire/plan', data: {
        'annual_expenses': _expenses.text,
        'swr': _swr.text,
        'current_value': _current.text,
        'monthly_contribution': _monthly.text,
        'expected_return': _return.text,
      });
      setState(() => _result = res.data as Map<String, dynamic>);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const DisclaimerStrip(),
        const SizedBox(height: 16),
        _field(_expenses, 'Jaarlijkse uitgaven (€)'),
        _field(_current, 'Huidige portefeuillewaarde (€)'),
        _field(_monthly, 'Maandelijkse inleg (€)'),
        Row(children: [
          Expanded(child: _field(_swr, 'SWR (0.04 = 4%)')),
          const SizedBox(width: 12),
          Expanded(child: _field(_return, 'Verwacht rendement')),
        ]),
        const SizedBox(height: 12),
        FilledButton(
          onPressed: _busy ? null : _compute,
          child: _busy ? const CircularProgressIndicator() : const Text('Bereken FIRE'),
        ),
        if (_error != null) Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
        if (_result != null) ...[
          const SizedBox(height: 20),
          _Targets(result: _result!),
        ],
      ],
    );
  }

  Widget _field(TextEditingController c, String label) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: TextField(
          controller: c,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: label),
        ),
      );
}

class _Targets extends StatelessWidget {
  const _Targets({required this.result});
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final t = result['targets'] as Map<String, dynamic>;
    final fiDate = result['fi_date'];
    final years = result['years_to_fi'];
    double n(Object? v) => double.tryParse('${v ?? 0}') ?? 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('FIRE-doelen', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            _row('Lean FIRE', Money.format(n(t['lean']))),
            _row('Coast FIRE', Money.format(n(t['coast']))),
            _row('Barista FIRE', Money.format(n(t['barista']))),
            _row('Fat FIRE', Money.format(n(t['fat']))),
            const Divider(),
            _row('Volledige FIRE', Money.format(n(t['full_number']))),
            const SizedBox(height: 8),
            if (fiDate != null) _row('Geschatte FI-datum', fiDate.toString()),
            if (years != null) _row('Jaren tot FI', n(years).toStringAsFixed(1)),
          ],
        ),
      ),
    );
  }

  Widget _row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [Text(label), Text(value, style: const TextStyle(fontWeight: FontWeight.w600))],
        ),
      );
}

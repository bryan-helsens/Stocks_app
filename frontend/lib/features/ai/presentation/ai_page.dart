import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../../core/widgets/disclaimer_strip.dart';
import '../../portfolio/data/portfolio_repository.dart';

/// AI Portfolio Analyst (M12): pick a provider, analyse the selected portfolio,
/// show summary + SWOT. Output is informational only (disclaimer always shown).
class AiPage extends ConsumerStatefulWidget {
  const AiPage({super.key});

  @override
  ConsumerState<AiPage> createState() => _AiPageState();
}

class _AiPageState extends ConsumerState<AiPage> {
  String _provider = 'OLLAMA';
  Map<String, dynamic>? _result;
  bool _busy = false;
  String? _error;

  Future<void> _analyze() async {
    final portfolios = await ref.read(portfoliosProvider.future);
    if (portfolios.isEmpty) {
      setState(() => _error = 'Maak eerst een portefeuille aan.');
      return;
    }
    final selected = ref.read(selectedPortfolioProvider) ?? portfolios.first.id;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await ref.read(apiClientProvider).raw.post('/ai/analyze/portfolio', data: {
        'portfolio_id': selected,
        'provider': _provider,
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
        Row(
          children: [
            const Text('Provider:'),
            const SizedBox(width: 12),
            DropdownButton<String>(
              value: _provider,
              items: const [
                DropdownMenuItem(value: 'OLLAMA', child: Text('Ollama (lokaal)')),
                DropdownMenuItem(value: 'OPENAI', child: Text('OpenAI')),
                DropdownMenuItem(value: 'CLAUDE', child: Text('Claude')),
              ],
              onChanged: (v) => setState(() => _provider = v ?? 'OLLAMA'),
            ),
            const Spacer(),
            FilledButton.icon(
              onPressed: _busy ? null : _analyze,
              icon: const Icon(Icons.auto_awesome),
              label: const Text('Analyseer'),
            ),
          ],
        ),
        if (_busy) const Padding(
          padding: EdgeInsets.all(32),
          child: Center(child: Text('AI denkt na…')),
        ),
        if (_error != null) Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
        if (_result != null) ...[
          const SizedBox(height: 16),
          _AiResult(result: _result!),
        ],
      ],
    );
  }
}

class _AiResult extends StatelessWidget {
  const _AiResult({required this.result});
  final Map<String, dynamic> result;

  List<String> _list(Object? v) =>
      (v as List?)?.map((e) => e.toString()).toList() ?? const [];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Samenvatting', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                Text(result['summary']?.toString() ?? ''),
                const SizedBox(height: 8),
                Text('Risicoscore: ${result['risk_score']}'),
                if ((result['concentration_note'] ?? '').toString().isNotEmpty)
                  Text(result['concentration_note'].toString()),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        _swot(context, 'Sterk', _list(result['strengths'])),
        _swot(context, 'Zwak', _list(result['weaknesses'])),
        _swot(context, 'Kansen', _list(result['opportunities'])),
        _swot(context, 'Bedreigingen', _list(result['threats'])),
        const SizedBox(height: 12),
        Text(result['disclaimer']?.toString() ?? '',
            style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }

  Widget _swot(BuildContext context, String title, List<String> items) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 6),
            for (final item in items) Text('• $item'),
          ],
        ),
      ),
    );
  }
}

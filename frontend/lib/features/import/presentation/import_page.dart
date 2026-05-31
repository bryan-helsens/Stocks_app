import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../portfolio/data/portfolio_repository.dart';

/// Broker import wizard (M4): pick source → upload → preview → commit.
class ImportPage extends ConsumerStatefulWidget {
  const ImportPage({super.key});

  @override
  ConsumerState<ImportPage> createState() => _ImportPageState();
}

class _ImportPageState extends ConsumerState<ImportPage> {
  String _parser = 'bux';
  Map<String, dynamic>? _preview;
  bool _busy = false;
  String? _error;
  String? _message;

  Future<void> _pickAndUpload() async {
    final portfolios = await ref.read(portfoliosProvider.future);
    if (portfolios.isEmpty) {
      setState(() => _error = 'Maak eerst een portefeuille aan (tab Portfolio).');
      return;
    }
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['csv', 'xlsx', 'pdf', 'txt'],
      withData: true,
    );
    if (picked == null || picked.files.single.bytes == null) return;
    final file = picked.files.single;

    setState(() {
      _busy = true;
      _error = null;
      _message = null;
    });
    try {
      final portfolioId = ref.read(selectedPortfolioProvider) ?? portfolios.first.id;
      final form = FormData.fromMap({
        'portfolio_id': portfolioId,
        'parser_key': _parser,
        'file': MultipartFile.fromBytes(file.bytes!, filename: file.name),
      });
      final res = await ref.read(apiClientProvider).raw.post('/imports', data: form);
      setState(() => _preview = res.data as Map<String, dynamic>);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _commit() async {
    final batchId = _preview?['batch_id'];
    if (batchId == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await ref.read(apiClientProvider).raw.post('/imports/$batchId/commit');
      setState(() {
        _message = (res.data as Map<String, dynamic>)['message']?.toString();
        _preview = null;
      });
      ref.invalidate(portfolioSummaryProvider);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = _preview;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Importeer transacties', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 12),
                Row(children: [
                  const Text('Bron:'),
                  const SizedBox(width: 12),
                  DropdownButton<String>(
                    value: _parser,
                    items: const [
                      DropdownMenuItem(value: 'bux', child: Text('BUX')),
                      DropdownMenuItem(value: 'csv_generic', child: Text('CSV')),
                      DropdownMenuItem(value: 'excel', child: Text('Excel')),
                      DropdownMenuItem(value: 'pdf', child: Text('PDF')),
                    ],
                    onChanged: (v) => setState(() => _parser = v ?? 'bux'),
                  ),
                  const Spacer(),
                  FilledButton.icon(
                    onPressed: _busy ? null : _pickAndUpload,
                    icon: const Icon(Icons.upload_file),
                    label: const Text('Kies bestand'),
                  ),
                ]),
              ],
            ),
          ),
        ),
        if (_busy) const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator())),
        if (_message != null) Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(_message!, style: const TextStyle(color: Colors.green)),
        ),
        if (_error != null) Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
        if (p != null) ...[
          const SizedBox(height: 16),
          _PreviewSummary(preview: p),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _busy ? null : _commit,
            child: Text('Commit ${p['new_count']} transacties'),
          ),
        ],
      ],
    );
  }
}

class _PreviewSummary extends StatelessWidget {
  const _PreviewSummary({required this.preview});
  final Map<String, dynamic> preview;

  @override
  Widget build(BuildContext context) {
    final rows = (preview['rows'] as List?) ?? const [];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Preview', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(spacing: 16, children: [
              _chip(context, 'Nieuw', preview['new_count'], Colors.green),
              _chip(context, 'Duplicaat', preview['dup_count'], Colors.orange),
              _chip(context, 'Ongeldig', preview['invalid_count'], Colors.red),
              _chip(context, 'Totaal', preview['row_count'], Colors.blueGrey),
            ]),
            const Divider(height: 24),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                columns: const [
                  DataColumn(label: Text('Status')),
                  DataColumn(label: Text('Datum')),
                  DataColumn(label: Text('Type')),
                  DataColumn(label: Text('Asset')),
                  DataColumn(label: Text('Aantal')),
                  DataColumn(label: Text('Bedrag')),
                ],
                rows: [
                  for (final r in rows.take(50))
                    DataRow(cells: [
                      DataCell(Text('${(r as Map)['status']}')),
                      DataCell(Text('${r['trade_date']}'.split('T').first)),
                      DataCell(Text('${r['type'] ?? '-'}')),
                      DataCell(Text('${r['ticker'] ?? r['isin'] ?? '-'}')),
                      DataCell(Text('${r['quantity'] ?? '-'}')),
                      DataCell(Text('${r['gross_amount'] ?? '-'} ${r['currency']}')),
                    ]),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _chip(BuildContext context, String label, Object? count, Color color) =>
      Chip(label: Text('$label: $count'), backgroundColor: color.withValues(alpha: 0.15));
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/async_value_view.dart';
import '../data/watchlist_repository.dart';

/// Watchlists (M15): create lists and view their items with target prices.
class WatchlistPage extends ConsumerWidget {
  const WatchlistPage({super.key});

  Future<void> _newList(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Nieuwe watchlist'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Naam'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuleer')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Aanmaken'),
          ),
        ],
      ),
    );
    if (name != null && name.isNotEmpty) {
      try {
        await ref.read(watchlistRepositoryProvider).create(name);
        ref.invalidate(watchlistsProvider);
      } on ApiException catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lists = ref.watch(watchlistsProvider);
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _newList(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Watchlist'),
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.refresh(watchlistsProvider.future),
        child: AsyncValueView<List<Watchlist>>(
          value: lists,
          onRetry: () => ref.refresh(watchlistsProvider),
          data: (items) {
            if (items.isEmpty) {
              return ListView(children: const [
                SizedBox(height: 120),
                Center(child: Text('Nog geen watchlists. Maak er een aan met +.')),
              ]);
            }
            return ListView(
              padding: const EdgeInsets.all(12),
              children: [for (final w in items) _WatchlistCard(watchlist: w)],
            );
          },
        ),
      ),
    );
  }
}

class _WatchlistCard extends ConsumerWidget {
  const _WatchlistCard({required this.watchlist});
  final Watchlist watchlist;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(_itemsProvider(watchlist.id));
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(watchlist.name, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            items.when(
              data: (list) => list.isEmpty
                  ? const Text('Geen items.')
                  : Column(
                      children: [
                        for (final i in list)
                          ListTile(
                            dense: true,
                            title: Text(i.assetId),
                            trailing: i.targetPrice != null
                                ? Text('Doel ${Money.format(i.targetPrice!)}')
                                : null,
                          ),
                      ],
                    ),
              loading: () => const Padding(
                padding: EdgeInsets.all(8),
                child: LinearProgressIndicator(),
              ),
              error: (_, __) => const Text('Kon items niet laden.'),
            ),
          ],
        ),
      ),
    );
  }
}

final _itemsProvider = FutureProvider.family<List<WatchlistItem>, String>(
  (ref, watchlistId) => ref.watch(watchlistRepositoryProvider).items(watchlistId),
);

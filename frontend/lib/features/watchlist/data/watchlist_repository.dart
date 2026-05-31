import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';

class Watchlist {
  const Watchlist({required this.id, required this.name});
  final String id;
  final String name;
  factory Watchlist.fromJson(Map<String, dynamic> j) =>
      Watchlist(id: j['id'] as String, name: j['name'] as String);
}

class WatchlistItem {
  const WatchlistItem({required this.id, required this.assetId, this.targetPrice, this.note});
  final String id;
  final String assetId;
  final double? targetPrice;
  final String? note;
  factory WatchlistItem.fromJson(Map<String, dynamic> j) => WatchlistItem(
        id: j['id'] as String,
        assetId: j['asset_id'] as String,
        targetPrice:
            j['target_price'] == null ? null : double.tryParse(j['target_price'].toString()),
        note: j['note'] as String?,
      );
}

class WatchlistRepository {
  WatchlistRepository(this._client);
  final ApiClient _client;

  Future<List<Watchlist>> list() async {
    final res = await _client.raw.get('/watchlists');
    return (res.data as List).map((e) => Watchlist.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Watchlist> create(String name) async {
    final res = await _client.raw.post('/watchlists', data: {'name': name});
    return Watchlist.fromJson(res.data as Map<String, dynamic>);
  }

  Future<List<WatchlistItem>> items(String watchlistId) async {
    final res = await _client.raw.get('/watchlists/$watchlistId/items');
    return (res.data as List).map((e) => WatchlistItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> addItem(String watchlistId, String assetId, double? targetPrice) async {
    await _client.raw.post('/watchlists/$watchlistId/items', data: {
      'asset_id': assetId,
      if (targetPrice != null) 'target_price': targetPrice.toString(),
    });
  }
}

final watchlistRepositoryProvider =
    Provider<WatchlistRepository>((ref) => WatchlistRepository(ref.watch(apiClientProvider)));

final watchlistsProvider =
    FutureProvider<List<Watchlist>>((ref) => ref.watch(watchlistRepositoryProvider).list());

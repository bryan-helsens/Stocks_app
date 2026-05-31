import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';

/// Quality score (M8) for an asset.
class AssetScore {
  const AssetScore({
    required this.ticker,
    required this.hasFundamentals,
    this.total,
    this.valuation,
    this.growth,
    this.health,
    this.dividend,
  });

  final String ticker;
  final bool hasFundamentals;
  final double? total;
  final double? valuation;
  final double? growth;
  final double? health;
  final double? dividend;

  static double? _n(Object? v) => v == null ? null : double.tryParse(v.toString());

  factory AssetScore.fromJson(Map<String, dynamic> j) => AssetScore(
        ticker: j['ticker'] as String,
        hasFundamentals: j['has_fundamentals'] as bool? ?? false,
        total: _n(j['total']),
        valuation: _n(j['valuation']),
        growth: _n(j['growth']),
        health: _n(j['health']),
        dividend: _n(j['dividend']),
      );
}

/// A single valuation model result (M9).
class ValuationItem {
  const ValuationItem({
    required this.method,
    required this.verdict,
    this.fairValue,
    this.currentPrice,
    this.marginOfSafety,
  });

  final String method;
  final String verdict;
  final double? fairValue;
  final double? currentPrice;
  final double? marginOfSafety;

  static double? _n(Object? v) => v == null ? null : double.tryParse(v.toString());

  factory ValuationItem.fromJson(Map<String, dynamic> j) => ValuationItem(
        method: j['method'] as String,
        verdict: j['verdict'] as String,
        fairValue: _n(j['fair_value']),
        currentPrice: _n(j['current_price']),
        marginOfSafety: _n(j['margin_of_safety']),
      );
}

class AnalysisRepository {
  AnalysisRepository(this._client);
  final ApiClient _client;

  Future<AssetScore> score(String assetId) async {
    final res = await _client.raw.get('/analysis/asset/$assetId/score');
    return AssetScore.fromJson(res.data as Map<String, dynamic>);
  }

  Future<List<ValuationItem>> valuation(String assetId, Map<String, dynamic> inputs) async {
    final res = await _client.raw.post('/analysis/asset/$assetId/valuation', data: inputs);
    final items = (res.data as Map<String, dynamic>)['items'] as List;
    return items.map((e) => ValuationItem.fromJson(e as Map<String, dynamic>)).toList();
  }
}

final analysisRepositoryProvider =
    Provider<AnalysisRepository>((ref) => AnalysisRepository(ref.watch(apiClientProvider)));

/// Score for a given asset id (family).
final assetScoreProvider =
    FutureProvider.family<AssetScore, String>((ref, assetId) async {
  return ref.watch(analysisRepositoryProvider).score(assetId);
});

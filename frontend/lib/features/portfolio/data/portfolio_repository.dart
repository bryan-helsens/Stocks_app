import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import 'portfolio_models.dart';

/// Data access for portfolios, holdings and transactions.
class PortfolioRepository {
  PortfolioRepository(this._client);

  final ApiClient _client;

  Future<List<Portfolio>> list() async {
    final res = await _client.raw.get('/portfolios');
    return (res.data as List)
        .map((e) => Portfolio.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Portfolio> create(String name, {String currency = 'EUR', bool isDefault = false}) async {
    final res = await _client.raw.post('/portfolios', data: {
      'name': name,
      'base_currency': currency,
      'is_default': isDefault,
    });
    return Portfolio.fromJson(res.data as Map<String, dynamic>);
  }

  Future<PortfolioSummary> summary(String portfolioId) async {
    final res = await _client.raw.get('/portfolios/$portfolioId/summary');
    return PortfolioSummary.fromJson(res.data as Map<String, dynamic>);
  }

  Future<void> addTransaction(Map<String, dynamic> body) async {
    await _client.raw.post('/transactions', data: body);
  }
}

final portfolioRepositoryProvider =
    Provider<PortfolioRepository>((ref) => PortfolioRepository(ref.watch(apiClientProvider)));

/// All portfolios for the current user.
final portfoliosProvider = FutureProvider<List<Portfolio>>(
  (ref) => ref.watch(portfolioRepositoryProvider).list(),
);

/// The currently selected portfolio id (defaults to the first/ default one).
final selectedPortfolioProvider = StateProvider<String?>((ref) => null);

/// Summary for the selected (or first available) portfolio.
final portfolioSummaryProvider = FutureProvider<PortfolioSummary?>((ref) async {
  final repo = ref.watch(portfolioRepositoryProvider);
  final portfolios = await ref.watch(portfoliosProvider.future);
  if (portfolios.isEmpty) return null;
  final selected = ref.watch(selectedPortfolioProvider) ?? portfolios.first.id;
  return repo.summary(selected);
});

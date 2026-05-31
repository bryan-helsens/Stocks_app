/// Plain immutable models for the portfolio feature.
///
/// Hand-written (instead of freezed) so the project compiles without running
/// build_runner. Decimal-precision numbers arrive as strings from the API and
/// are parsed to double for display only (never for authoritative maths, which
/// the backend performs).
library;

double _d(Object? v) => v == null ? 0 : double.tryParse(v.toString()) ?? 0;
double? _dn(Object? v) => v == null ? null : double.tryParse(v.toString());

class Portfolio {
  const Portfolio({
    required this.id,
    required this.name,
    required this.baseCurrency,
    required this.isDefault,
    this.description,
  });

  final String id;
  final String name;
  final String baseCurrency;
  final bool isDefault;
  final String? description;

  factory Portfolio.fromJson(Map<String, dynamic> j) => Portfolio(
        id: j['id'] as String,
        name: j['name'] as String,
        baseCurrency: j['base_currency'] as String? ?? 'EUR',
        isDefault: j['is_default'] as bool? ?? false,
        description: j['description'] as String?,
      );
}

class AssetRef {
  const AssetRef({
    required this.ticker,
    required this.name,
    required this.assetClass,
    this.id,
    this.sector,
    this.country,
    this.currency = 'USD',
  });

  final String? id;
  final String ticker;
  final String name;
  final String assetClass;
  final String? sector;
  final String? country;
  final String currency;

  factory AssetRef.fromJson(Map<String, dynamic> j) => AssetRef(
        id: j['id'] as String?,
        ticker: j['ticker'] as String,
        name: j['name'] as String,
        assetClass: j['asset_class'] as String,
        sector: j['sector'] as String?,
        country: j['country'] as String?,
        currency: j['currency'] as String? ?? 'USD',
      );
}

class Holding {
  const Holding({
    required this.asset,
    required this.quantity,
    required this.avgCost,
    required this.totalInvested,
    required this.realizedPnl,
    this.price,
    this.marketValue,
    this.unrealizedPnl,
    this.unrealizedPct,
  });

  final AssetRef asset;
  final double quantity;
  final double avgCost;
  final double totalInvested;
  final double realizedPnl;
  final double? price;
  final double? marketValue;
  final double? unrealizedPnl;
  final double? unrealizedPct;

  factory Holding.fromJson(Map<String, dynamic> j) => Holding(
        asset: AssetRef.fromJson(j['asset'] as Map<String, dynamic>),
        quantity: _d(j['quantity']),
        avgCost: _d(j['avg_cost']),
        totalInvested: _d(j['total_invested']),
        realizedPnl: _d(j['realized_pnl']),
        price: _dn(j['price']),
        marketValue: _dn(j['market_value']),
        unrealizedPnl: _dn(j['unrealized_pnl']),
        unrealizedPct: _dn(j['unrealized_pct']),
      );
}

class PortfolioSummary {
  const PortfolioSummary({
    required this.portfolioId,
    required this.name,
    required this.baseCurrency,
    required this.totalValue,
    required this.totalInvested,
    required this.totalUnrealized,
    required this.realizedPnl,
    required this.holdings,
  });

  final String portfolioId;
  final String name;
  final String baseCurrency;
  final double totalValue;
  final double totalInvested;
  final double totalUnrealized;
  final double realizedPnl;
  final List<Holding> holdings;

  double get unrealizedPct => totalInvested > 0 ? totalUnrealized / totalInvested : 0;

  factory PortfolioSummary.fromJson(Map<String, dynamic> j) => PortfolioSummary(
        portfolioId: j['portfolio_id'] as String,
        name: j['name'] as String,
        baseCurrency: j['base_currency'] as String? ?? 'EUR',
        totalValue: _d(j['total_value']),
        totalInvested: _d(j['total_invested']),
        totalUnrealized: _d(j['total_unrealized']),
        realizedPnl: _d(j['realized_pnl']),
        holdings: (j['holdings'] as List)
            .map((e) => Holding.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

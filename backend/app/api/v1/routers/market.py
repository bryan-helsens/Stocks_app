"""Market data & asset endpoints (search, resolve, quotes)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.infrastructure.db.repositories import SqlAssetRepository
from app.infrastructure.market_data import get_market_data_provider
from app.schemas.portfolio import AssetResponse

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/search", response_model=list[AssetResponse])
async def search_assets(
    _: CurrentUser, session: SessionDep, q: str = Query(min_length=1)
) -> list[AssetResponse]:
    """Search known assets locally, falling back to the market provider."""
    repo = SqlAssetRepository(session)
    local = await repo.search(q)
    if local:
        return [
            AssetResponse(
                id=a.id, ticker=a.ticker, name=a.name, asset_class=a.asset_class,
                isin=a.isin, sector=a.sector, country=a.country, currency=a.currency,
            )
            for a in local
        ]
    provider = get_market_data_provider()
    infos = await provider.search(q)
    return [
        AssetResponse(
            id=None, ticker=i.symbol, name=i.name, asset_class=_safe_class(i.asset_class),
            isin=i.isin, sector=i.sector, country=i.country, currency=i.currency,
        )
        for i in infos
    ]


def _safe_class(raw: str):
    from app.domain.value_objects.enums import AssetClass

    try:
        return AssetClass(raw)
    except ValueError:
        return AssetClass.STOCK

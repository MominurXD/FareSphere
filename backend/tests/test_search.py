from datetime import date

from app.models import SearchRequest
from app.services.sample_search import search


def request(sort="best", bags=0):
    return SearchRequest(
        origin="LON",
        destination="BCN",
        departure_date=date(2026, 11, 14),
        passengers=1,
        checked_bags=bags,
        flexible_days=2,
        sort=sort,
    )


def test_sample_mode_is_explicitly_marked():
    result = search(request())
    assert result.data_mode == "sample"
    assert result.providers_used == ["Sample data"]
    assert all(not journey.price_verified for journey in result.results)
    assert all(not leg.price_verified for journey in result.results for leg in journey.legs)


def test_cheapest_sort_puts_lowest_price_first():
    result = search(request(sort="cheapest"))
    prices = [item.total_price for item in result.results]
    assert prices == sorted(prices)


def test_search_surfaces_sample_savings():
    result = search(request(sort="cheapest"))
    assert result.results[0].savings_vs_baseline > 0
    assert len(result.flexible_date_savings) == 5


def test_baggage_changes_sample_total_cost():
    without_bag = search(request(sort="cheapest", bags=0))
    with_bag = search(request(sort="cheapest", bags=1))
    assert min(item.total_price for item in with_bag.results) >= min(item.total_price for item in without_bag.results)

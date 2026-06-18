from polovni_monitor.config import load_config
from polovni_monitor.deal import evaluate_deal
from polovni_monitor.models import Ad


def _cfg():
    cfg = load_config()
    cfg.deal_price_eur = 12500
    cfg.deal_mileage_km = 130000
    cfg.deal_year_from = 2020
    cfg.deal_min_score = 3
    return cfg


def test_great_deal_without_chain():
    cfg = _cfg()
    ad = Ad(ad_id="1", url="x", price=11999, year=2022, mileage=95000)
    res = evaluate_deal(ad, cfg, "")
    # great price (+2) + very low mileage (+2) + recent year (+1) = 5
    assert res.score >= cfg.deal_min_score
    assert any("price" in r for r in res.reasons)
    assert any("mileage" in r for r in res.reasons)


def test_origin_bonus_diacritics_insensitive():
    cfg = _cfg()
    ad = Ad(ad_id="2", url="x", price=13900, year=2019, mileage=150000)
    res = evaluate_deal(ad, cfg, "prvi vlasnik, kupljen u srbiji")
    assert "first owner" in res.reasons
    assert "bought in Serbia" in res.reasons


def test_weak_listing_below_threshold():
    cfg = _cfg()
    ad = Ad(ad_id="3", url="x", price=13900, year=2019, mileage=180000)
    res = evaluate_deal(ad, cfg, "")
    # price above deal threshold, high mileage, older year -> no points
    assert res.score < cfg.deal_min_score

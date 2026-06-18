from polovni_monitor.parser import parse_mileage, parse_price


def test_price_with_dot():
    assert parse_price("Cena: 13.500 €") == 13500


def test_price_plain():
    assert parse_price("13500 €") == 13500


def test_price_with_space():
    assert parse_price("13 500 €") == 13500


def test_price_missing():
    assert parse_price("Cena na upit") is None


def test_mileage_variants():
    assert parse_mileage("162.000 km") == 162000
    assert parse_mileage("162000 km") == 162000
    assert parse_mileage("162 000 km") == 162000

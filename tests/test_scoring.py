from polovni_monitor.scoring import analyze_text


def test_strong_signal_chain():
    result = analyze_text("Auto je odlično, zamenjen lanac na 100.000 km.")
    assert result.score >= 3
    assert "zamenjen lanac" in result.positive_hits


def test_weak_signal_service():
    result = analyze_text("Redovno rađen veliki servis u ovlašćenom servisu.")
    assert result.score >= 1
    assert "veliki servis" in result.weak_hits


def test_negative_signal():
    result = analyze_text("Nije menjan lanac, kupac da proveri.")
    assert result.score < 0
    assert "nije menjan lanac" in result.negative_hits


def test_diacritics_with_and_without():
    with_dia = analyze_text("Kaiš u ulju zamenjen prošle godine.")
    without_dia = analyze_text("Kais u ulju zamenjen prosle godine.")
    assert with_dia.score >= 3
    assert without_dia.score >= 3
    assert with_dia.score == without_dia.score


def test_single_signal_counted_once():
    # Repeating the same signal must not multiply the score.
    result = analyze_text("lanac lanac lanac")
    assert result.score == 3


def test_no_substring_false_positive():
    # "razvod"/"lanac" are strong keywords, but word-boundary matching must not
    # fire on a longer unrelated word like "razvodnik" (distributor).
    result = analyze_text("Menjam auto zbog razvodnika u motoru.")
    assert result.positive_hits == []
    assert result.score == 0

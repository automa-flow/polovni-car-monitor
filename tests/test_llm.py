from polovni_monitor.llm import parse_verdict


def test_parse_full_verdict():
    raw = (
        '{"chain_belt_status": "yes", '
        '"chain_belt_note": "owner states the timing chain was replaced", '
        '"worth_sending": true, '
        '"summary": "Clean C5 Aircross with documented chain service.", '
        '"suspicious": ["price seems low"], '
        '"highlights": ["full service history"]}'
    )
    v = parse_verdict(raw)
    assert v.chain_belt_status == "yes"
    assert v.worth_sending is True
    assert v.suspicious == ["price seems low"]
    assert v.highlights == ["full service history"]
    assert v.available is True


def test_parse_defaults_and_status_normalization():
    v = parse_verdict('{"chain_belt_status": "maybe", "worth_sending": false}')
    # unknown status normalizes to "unclear"
    assert v.chain_belt_status == "unclear"
    assert v.worth_sending is False
    # missing note falls back to a sensible default
    assert v.chain_belt_note == "not mentioned in the ad"
    # missing lists default to empty
    assert v.suspicious == []
    assert v.highlights == []


def test_parse_coerces_string_lists():
    v = parse_verdict(
        '{"chain_belt_status": "no", "suspicious": "salvage title"}'
    )
    assert v.chain_belt_status == "no"
    assert v.suspicious == ["salvage title"]

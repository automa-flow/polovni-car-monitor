import pytest

from polovni_monitor.utils import redact_contacts


@pytest.mark.parametrize(
    "text",
    [
        "zvati 064/123-45-67",
        "zvati 064 123 4567",
        "zvati 0641234567",
        "zvati 064-123-4567",
        "fiksni 011/123-4567",
        "zvati +381 64 123 4567",
        "zvati +381641234567",
        "zvati 00381 64 123 4567",
        "zvati +381 (0) 64 123 4567",
    ],
)
def test_phone_numbers_are_masked(text):
    out = redact_contacts(text)
    assert "[phone]" in out
    assert "123" not in out


def test_email_is_masked():
    assert redact_contacts("pišite na prodavac.auto@example.co.rs") == "pišite na [email]"


@pytest.mark.parametrize(
    "text",
    [
        "Cena 13.550 €",
        "Kilometraža 146.930 km",
        "Servis rađen 01.06.2025.",
        "Registrovan do 05.2026",
        "Godište 2020, 1499 cm3, 96/131 kW/KS",
        "VIN VR7ACYHZSLL000000",
    ],
)
def test_non_contact_numbers_are_kept(text):
    assert redact_contacts(text) == text


def test_empty_text():
    assert redact_contacts("") == ""

import pytest

from polovni_monitor.config import load_config


@pytest.mark.parametrize(
    ("env", "field", "expected"),
    [
        ({"CHECK_INTERVAL_MIN": "1"}, "check_interval_min", 15),
        ({"CHECK_INTERVAL_MIN": "60"}, "check_interval_min", 60),
        ({"NIGHT_INTERVAL_MIN": "5"}, "night_interval_min", 15),
        ({"REQUEST_DELAY_SEC": "0"}, "request_delay_sec", 2.0),
        ({"REQUEST_DELAY_SEC": "3.5"}, "request_delay_sec", 3.5),
        ({"FETCH_RETRIES": "10"}, "fetch_retries", 3),
        ({"FETCH_RETRIES": "0"}, "fetch_retries", 1),
        ({"RECHECK_KNOWN_HOURS": "1"}, "recheck_known_hours", 24),
        ({"RECHECK_KNOWN_HOURS": "48"}, "recheck_known_hours", 48),
        ({"RECHECK_KNOWN_HOURS": "0"}, "recheck_known_hours", 0),
    ],
)
def test_politeness_limits_are_enforced(monkeypatch, env, field, expected):
    # Real environment variables take precedence over the local .env file.
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert getattr(load_config(), field) == expected

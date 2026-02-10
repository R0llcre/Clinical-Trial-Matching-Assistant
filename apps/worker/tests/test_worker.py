from worker import _env_bool, _env_int, _split_csv


def test_env_int_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TEST_INT", raising=False)
    assert _env_int("TEST_INT", 7) == 7


def test_env_int_invalid(monkeypatch) -> None:
    monkeypatch.setenv("TEST_INT", "oops")
    assert _env_int("TEST_INT", 9) == 9


def test_env_bool_variants(monkeypatch) -> None:
    monkeypatch.setenv("TEST_BOOL", "true")
    assert _env_bool("TEST_BOOL") is True
    monkeypatch.setenv("TEST_BOOL", "0")
    assert _env_bool("TEST_BOOL") is False


def test_split_csv() -> None:
    assert _split_csv("cancer") == ["cancer"]
    assert _split_csv("cancer, asthma , , heart failure") == [
        "cancer",
        "asthma",
        "heart failure",
    ]

from worker import _env_bool, _env_int


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

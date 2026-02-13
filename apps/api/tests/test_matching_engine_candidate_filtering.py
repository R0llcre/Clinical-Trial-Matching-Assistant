from app.services import matching_engine


def test_match_trials_passes_filters_into_candidate_loader(monkeypatch) -> None:
    captured = {}

    def _fake_loader(
        engine,
        *,
        condition_filter: str = "",
        status_filter: str = "",
        phase_filter: str = "",
        country_filter: str = "",
        state_filter: str = "",
        city_filter: str = "",
        recall_limit: int = 500,
    ):
        captured["condition_filter"] = condition_filter
        captured["status_filter"] = status_filter
        captured["phase_filter"] = phase_filter
        captured["country_filter"] = country_filter
        captured["state_filter"] = state_filter
        captured["city_filter"] = city_filter
        captured["recall_limit"] = recall_limit
        return []

    monkeypatch.setattr(matching_engine, "_load_trial_candidates", _fake_loader)

    results = matching_engine.match_trials(
        engine=object(),
        patient_profile={},
        filters={
            "condition": " melanoma ",
            "status": "RECRUITING",
            "phase": "PHASE2",
            "country": "United States",
            "state": "New York",
            "city": "New York",
        },
        top_k=10,
    )

    assert results == []
    assert captured["condition_filter"] == "melanoma"
    assert captured["status_filter"] == "RECRUITING"
    assert captured["phase_filter"] == "PHASE2"
    assert captured["country_filter"] == "United States"
    assert captured["state_filter"] == "New York"
    assert captured["city_filter"] == "New York"
    assert captured["recall_limit"] == 4000


def test_match_trials_uses_default_recall_limit_when_unfiltered(monkeypatch) -> None:
    captured = {}

    def _fake_loader(
        engine,
        *,
        condition_filter: str = "",
        status_filter: str = "",
        phase_filter: str = "",
        country_filter: str = "",
        state_filter: str = "",
        city_filter: str = "",
        recall_limit: int = 500,
    ):
        captured["recall_limit"] = recall_limit
        return []

    monkeypatch.setattr(matching_engine, "_load_trial_candidates", _fake_loader)

    results = matching_engine.match_trials(
        engine=object(),
        patient_profile={},
        filters={},
        top_k=10,
    )

    assert results == []
    assert captured["recall_limit"] == 500

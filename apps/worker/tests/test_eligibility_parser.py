from services.eligibility_parser import preprocess_eligibility_text


def test_preprocess_splits_inclusion_and_exclusion_sections() -> None:
    text = """
    Inclusion Criteria:
    - Adults aged 18 years or older.
    - Histologically confirmed disease.

    Exclusion Criteria:
    1. Pregnant or breastfeeding.
    2. Prior treatment in the last 30 days.
    """

    payload = preprocess_eligibility_text(text)

    assert payload["inclusion_sentences"] == [
        "Adults aged 18 years or older.",
        "Histologically confirmed disease.",
    ]
    assert payload["exclusion_sentences"] == [
        "Pregnant or breastfeeding.",
        "Prior treatment in the last 30 days.",
    ]


def test_preprocess_handles_inline_headings() -> None:
    text = """
    Inclusion: Male or female participants.
    Exclusion: Active infection.
    """

    payload = preprocess_eligibility_text(text)

    assert payload["inclusion_sentences"] == ["Male or female participants."]
    assert payload["exclusion_sentences"] == ["Active infection."]


def test_preprocess_without_sections_defaults_to_single_segment() -> None:
    text = """
    Adults aged 21 years or older.
    ECOG <= 2.
    """

    payload = preprocess_eligibility_text(text)

    assert payload["inclusion_sentences"] == [
        "Adults aged 21 years or older.",
        "ECOG <= 2.",
    ]
    assert payload["exclusion_sentences"] == []


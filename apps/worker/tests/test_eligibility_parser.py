from services.eligibility_parser import parse_criteria_v1, preprocess_eligibility_text


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


def test_preprocess_handles_mixed_inline_heading_in_single_line() -> None:
    text = (
        "Inclusion: Adults with heart failure. "
        "Exclusion: Prior treatment within the last 30 days."
    )

    payload = preprocess_eligibility_text(text)

    assert payload["inclusion_sentences"] == ["Adults with heart failure."]
    assert payload["exclusion_sentences"] == ["Prior treatment within the last 30 days."]


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


def test_parse_criteria_v1_builds_age_sex_and_exclusion_rules() -> None:
    text = """
    Inclusion Criteria:
    Participants must be 18 years or older.
    Female participants only.
    Exclusion Criteria:
    Pregnant or breastfeeding participants.
    """

    rules = parse_criteria_v1(text)

    assert all(rule.get("evidence_text") for rule in rules)

    age_rule = next(
        rule
        for rule in rules
        if rule["field"] == "age" and rule["operator"] == ">=" and rule["type"] == "INCLUSION"
    )
    assert age_rule["value"] == 18
    assert age_rule["unit"] == "years"

    sex_rule = next(
        rule
        for rule in rules
        if rule["field"] == "sex" and rule["type"] == "INCLUSION"
    )
    assert sex_rule["value"] == "female"

    exclusion_fields = {
        rule["value"]
        for rule in rules
        if rule["type"] == "EXCLUSION" and rule["operator"] in {"NO_HISTORY", "WITHIN_LAST"}
    }
    assert "pregnancy" in exclusion_fields
    assert "breastfeeding" in exclusion_fields


def test_parse_criteria_v1_returns_unknown_when_sentence_cannot_be_parsed() -> None:
    text = """
    Inclusion Criteria:
    Participant must sign informed consent before enrollment.
    """

    rules = parse_criteria_v1(text)

    assert len(rules) == 1
    assert rules[0]["type"] == "INCLUSION"
    assert rules[0]["field"] == "other"
    assert rules[0]["operator"] == "EXISTS"
    assert rules[0]["certainty"] == "low"


def test_parse_criteria_v1_deduplicates_overlapping_infection_keywords() -> None:
    text = """
    Exclusion Criteria:
    Active infection.
    """

    rules = parse_criteria_v1(text)

    infection_rules = [
        rule
        for rule in rules
        if rule["type"] == "EXCLUSION"
        and rule["field"] == "condition"
        and rule["value"] == "active infection"
    ]
    assert len(infection_rules) == 1


def test_parse_criteria_v1_extracts_lab_and_condition_rules() -> None:
    text = """
    Inclusion: Adults with heart failure. HbA1c <= 8.5%.
    """

    rules = parse_criteria_v1(text)

    condition_rule = next(
        rule
        for rule in rules
        if rule["type"] == "INCLUSION"
        and rule["field"] == "condition"
        and rule["operator"] == "IN"
    )
    assert condition_rule["value"] == "heart failure"

    lab_rule = next(
        rule
        for rule in rules
        if rule["type"] == "INCLUSION"
        and rule["field"] == "lab"
        and rule["operator"] == "<="
    )
    assert lab_rule["value"] == 8.5
    assert lab_rule["unit"] == "%"


def test_parse_criteria_v1_does_not_parse_month_window_as_age() -> None:
    text = """
    Inclusion Criteria:
    long covid symptoms for at least 3 months.
    """

    rules = parse_criteria_v1(text)

    age_rules = [rule for rule in rules if rule["field"] == "age"]
    assert age_rules == []


def test_parse_criteria_v1_extracts_duration_as_other_rule() -> None:
    text = """
    Inclusion Criteria:
    long covid symptoms for at least 3 months.
    """

    rules = parse_criteria_v1(text)

    duration_rule = next(
        rule
        for rule in rules
        if rule["type"] == "INCLUSION"
        and rule["field"] == "other"
        and rule["operator"] == "EXISTS"
    )
    assert duration_rule["evidence_text"].lower() == "for at least 3 months"

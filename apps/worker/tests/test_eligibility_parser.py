from services import eligibility_parser
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
    Female participants who are pregnant or breastfeeding.
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

    exclusion_sex_rule = next(
        rule
        for rule in rules
        if rule["type"] == "EXCLUSION"
        and rule["field"] == "sex"
        and rule["operator"] == "="
    )
    assert exclusion_sex_rule["value"] == "female"


def test_parse_criteria_v1_emits_placeholder_when_inclusion_sentence_unparsed() -> None:
    text = """
    Inclusion Criteria:
    Participant must sign informed consent before enrollment.
    """

    rules = parse_criteria_v1(text)

    assert len(rules) == 1
    assert rules[0]["type"] == "INCLUSION"
    assert rules[0]["field"] == "condition"
    assert rules[0]["operator"] == "IN"
    assert rules[0]["value"] == "study specific condition"


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


def test_parse_criteria_v1_extracts_exclusion_history_and_hiv_conditions() -> None:
    text = """
    Exclusion Criteria:
    History of cirrhosis.
    Known infection with Hepatitis B or C, or HIV.
    """

    rules = parse_criteria_v1(text)
    values = {
        rule["value"]
        for rule in rules
        if rule["type"] == "EXCLUSION"
        and rule["field"] == "condition"
        and rule["operator"] == "NOT_IN"
    }
    assert "cirrhosis" in values
    assert "hiv positive" in values


def test_parse_criteria_v1_extracts_generic_exclusion_condition() -> None:
    text = """
    Exclusion Criteria:
    patients with diabetes.
    """

    rules = parse_criteria_v1(text)
    assert any(
        rule["type"] == "EXCLUSION"
        and rule["field"] == "condition"
        and rule["operator"] == "NOT_IN"
        and rule["value"] == "diabetes"
        for rule in rules
    )


def test_parse_criteria_v1_extracts_fertile_condition_hint() -> None:
    text = """
    Inclusion Criteria:
    Fertile adults are eligible.
    """

    rules = parse_criteria_v1(text)
    values = {
        rule["value"]
        for rule in rules
        if rule["type"] == "INCLUSION"
        and rule["field"] == "condition"
        and rule["operator"] == "IN"
    }
    assert "fertile" in values
    assert "adult" not in values


def test_parse_criteria_v1_extracts_exclusion_history_within_last() -> None:
    text = """
    Exclusion Criteria:
    Tobacco use within the last 3 months.
    """

    rules = parse_criteria_v1(text)
    history_rule = next(
        rule
        for rule in rules
        if rule["type"] == "EXCLUSION"
        and rule["field"] == "history"
        and rule["operator"] == "WITHIN_LAST"
    )
    assert history_rule["value"] == 3
    assert history_rule["unit"] == "months"


def test_parse_criteria_v1_extracts_given_birth_history_rule() -> None:
    text = """
    Exclusion Criteria:
    If female, is pregnant or has given birth within the last six weeks.
    """

    rules = parse_criteria_v1(text)
    pregnancy_history_rule = next(
        rule
        for rule in rules
        if rule["type"] == "EXCLUSION"
        and rule["field"] == "history"
        and rule["operator"] == "NO_HISTORY"
    )
    assert pregnancy_history_rule["value"] == "pregnancy"


def test_parse_criteria_v1_does_not_emit_sex_all_for_mixed_sex_sentence() -> None:
    text = """
    Inclusion Criteria:
    Male or female participants are eligible.
    """

    rules = parse_criteria_v1(text)
    sex_rules = [rule for rule in rules if rule["field"] == "sex"]
    assert sex_rules == []


def test_parse_criteria_v1_adds_study_specific_condition_when_heading_only() -> None:
    text = """
    Inclusion Criteria:
    - Able to provide informed consent.
    Exclusion Criteria:
    - None.
    """

    rules = parse_criteria_v1(text)
    placeholder = next(
        rule
        for rule in rules
        if rule["type"] == "INCLUSION"
        and rule["field"] == "condition"
        and rule["value"] == "study specific condition"
    )
    assert placeholder["operator"] == "IN"
    assert placeholder["evidence_text"] == "Inclusion Criteria:"


def test_parse_criteria_v1_parses_at_least_years_of_age_pattern() -> None:
    text = """
    Inclusion Criteria:
    Participants must be at least 18 years of age.
    """

    rules = parse_criteria_v1(text)
    age_rule = next(
        rule
        for rule in rules
        if rule["field"] == "age"
        and rule["operator"] == ">="
        and rule["type"] == "INCLUSION"
    )
    assert age_rule["value"] == 18
    assert age_rule["unit"] == "years"


def test_parse_criteria_v1_does_not_emit_other_for_duration_only_sentence() -> None:
    text = """
    Inclusion Criteria:
    long covid symptoms for at least 3 months.
    """

    rules = parse_criteria_v1(text)

    assert all(rule["field"] != "other" for rule in rules)
    assert any(
        rule["field"] == "condition"
        and rule["operator"] == "IN"
        and rule["value"] == "long covid"
        for rule in rules
    )


def test_parse_criteria_v1_curated_override_enabled_by_default(monkeypatch) -> None:
    text = "Inclusion Criteria: Adults with asthma."
    override_rule = {
        "type": "INCLUSION",
        "field": "condition",
        "operator": "IN",
        "value": "override condition",
        "unit": None,
        "evidence_text": "Inclusion Criteria: Adults with asthma.",
    }
    monkeypatch.delenv("CTMA_ENABLE_CURATED_PARSER_OVERRIDES", raising=False)
    monkeypatch.setattr(
        eligibility_parser,
        "_CURATED_RULE_OVERRIDES_BY_TEXT",
        {eligibility_parser._norm_text(text): [override_rule]},
    )

    rules = parse_criteria_v1(text)
    assert len(rules) == 1
    assert rules[0]["value"] == "override condition"


def test_parse_criteria_v1_curated_override_enabled(monkeypatch) -> None:
    text = "Inclusion Criteria: Adults with asthma."
    override_rule = {
        "type": "INCLUSION",
        "field": "condition",
        "operator": "IN",
        "value": "override condition",
        "unit": None,
        "evidence_text": "Inclusion Criteria: Adults with asthma.",
    }
    monkeypatch.setenv("CTMA_ENABLE_CURATED_PARSER_OVERRIDES", "1")
    monkeypatch.setattr(
        eligibility_parser,
        "_CURATED_RULE_OVERRIDES_BY_TEXT",
        {eligibility_parser._norm_text(text): [override_rule]},
    )

    rules = parse_criteria_v1(text)
    assert len(rules) == 1
    assert rules[0]["value"] == "override condition"


def test_parse_criteria_v1_curated_override_disabled_with_env_zero(monkeypatch) -> None:
    text = "Inclusion Criteria: Adults with asthma."
    override_rule = {
        "type": "INCLUSION",
        "field": "condition",
        "operator": "IN",
        "value": "override condition",
        "unit": None,
        "evidence_text": "Inclusion Criteria: Adults with asthma.",
    }
    monkeypatch.setenv("CTMA_ENABLE_CURATED_PARSER_OVERRIDES", "0")
    monkeypatch.setattr(
        eligibility_parser,
        "_CURATED_RULE_OVERRIDES_BY_TEXT",
        {eligibility_parser._norm_text(text): [override_rule]},
    )

    rules = parse_criteria_v1(text)
    values = {rule["value"] for rule in rules if rule["field"] == "condition"}
    assert "override condition" not in values

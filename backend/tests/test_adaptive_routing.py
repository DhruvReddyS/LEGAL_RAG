from app.services.adaptive_routing import route_legal_query


def test_explicit_modes_are_never_overridden() -> None:
    assert route_legal_query(query="Draft a defence strategy", requested_mode="fast").selected_mode == "fast"
    assert route_legal_query(query="What is an FIR?", requested_mode="deep").selected_mode == "deep"


def test_auto_routes_focused_lookup_to_fast() -> None:
    decision = route_legal_query(query="How do I report a missing dog to police?", requested_mode="auto")
    assert decision.selected_mode == "fast"
    assert decision.reason == "focused_authority_lookup"


def test_auto_routes_defence_scenario_to_deep() -> None:
    decision = route_legal_query(
        query="Analyse this case scenario and identify defence loopholes, weaknesses and counterarguments.",
        requested_mode="auto",
    )
    assert decision.selected_mode == "deep"
    assert "defence_strategy" in decision.signals


def test_auto_routes_case_scoped_query_to_deep() -> None:
    decision = route_legal_query(query="What applies?", requested_mode="auto", case_id="case-123")
    assert decision.selected_mode == "deep"
    assert "case_scoped_matter" in decision.signals


def test_auto_routes_multi_question_query_to_deep() -> None:
    decision = route_legal_query(
        query="Was the arrest lawful? Was the search evidence admissible?",
        requested_mode="auto",
    )
    assert decision.selected_mode == "deep"
    assert "multiple_questions" in decision.signals


def test_auto_routes_private_actor_constitutional_applicability_to_deep() -> None:
    decision = route_legal_query(
        query="Does Article 14 directly apply to a private employer accused of caste discrimination?",
        requested_mode="auto",
    )
    assert decision.selected_mode == "deep"
    assert "constitutional_applicability" in decision.signals

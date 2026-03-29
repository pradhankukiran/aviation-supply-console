from aviation_supply_console.services.classification import classify_aircraft


def test_business_jet_type_is_charter_relevant() -> None:
    classification = classify_aircraft(type_code="C56X", reg="N900EX", category="A3")
    assert classification.charter_relevant is True
    assert classification.aircraft_class == "midsize_jet"


def test_airliner_type_is_excluded() -> None:
    classification = classify_aircraft(type_code="A320", reg="N123AB", category="A5")
    assert classification.charter_relevant is False
    assert classification.reason == "airliner_type"


def test_regional_airliner_type_is_excluded() -> None:
    classification = classify_aircraft(type_code="E75L", reg="N407YX", category="A3")
    assert classification.charter_relevant is False
    assert classification.reason == "airliner_type"


def test_piston_type_is_excluded() -> None:
    classification = classify_aircraft(type_code="C172", reg="N5169E", category="A1")
    assert classification.charter_relevant is False
    assert classification.reason == "piston_type"

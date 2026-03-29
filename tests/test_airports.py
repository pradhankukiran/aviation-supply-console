from aviation_supply_console.services.airports import resolve_airport


def test_resolve_airport_accepts_iata_and_icao() -> None:
    assert resolve_airport("TEB")["icao"] == "KTEB"
    assert resolve_airport("KOPF")["iata"] == "OPF"

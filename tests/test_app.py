from fastapi.testclient import TestClient

from aviation_supply_console.app import create_app


def test_home_page_loads() -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert "Aviation Supply Console" in response.text


def test_map_page_loads() -> None:
    client = TestClient(create_app())
    response = client.get("/map")
    assert response.status_code == 200
    assert "Ops Map" in response.text


def test_aircraft_detail_page_loads() -> None:
    client = TestClient(create_app())
    response = client.get("/aircraft/test123")
    assert response.status_code == 200
    assert "Aircraft test123" in response.text

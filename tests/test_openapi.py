from fastapi.testclient import TestClient

from blackglass.app import create_app
from blackglass.config import Settings


def test_openapi_schema_has_expected_version_and_paths() -> None:
    client = TestClient(create_app(Settings()))

    schema = client.get("/openapi.json").json()

    assert schema["openapi"] == "3.1.0"
    assert "/health" in schema["paths"]
    assert "/retrieve" in schema["paths"]
    assert "/artifacts/{artifact_id}" not in schema["paths"]


def test_retrieve_openapi_contract_is_agent_friendly() -> None:
    client = TestClient(create_app(Settings()))

    operation = client.get("/openapi.json").json()["paths"]["/retrieve"]["post"]

    assert operation["operationId"] == "retrieveUrl"
    assert operation["tags"] == ["retrieval"]
    assert operation["summary"] == "Retrieve one URL"
    assert "422" in operation["responses"]
    assert (
        operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/RetrieveRequest"
    )
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/RetrieveResponse"
    )
    assert "examples" in operation["requestBody"]["content"]["application/json"]


def test_health_openapi_contract_has_stable_metadata() -> None:
    client = TestClient(create_app(Settings()))

    operation = client.get("/openapi.json").json()["paths"]["/health"]["get"]

    assert operation["operationId"] == "getHealth"
    assert operation["tags"] == ["health"]
    assert operation["summary"] == "Check service health"


def test_docs_are_enabled() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/docs")

    assert response.status_code == 200
    assert "Swagger UI" in response.text

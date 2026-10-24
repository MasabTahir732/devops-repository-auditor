from app import app


def test_health():
    with app.test_client() as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}

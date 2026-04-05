from app.models.url import ShortenedURL


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_shorten_url(client, seed_data):
    response = client.post("/shorten", json={"url": "https://newsite.com"})
    assert response.status_code == 201
    data = response.get_json()
    assert "short_code" in data
    assert len(data["short_code"]) == 6


def test_shorten_missing_url(client, seed_data):
    response = client.post("/shorten", json={})
    assert response.status_code == 400
    assert response.get_json() == {"error": "URL is required"}


def test_redirect(client, seed_data):
    response = client.get("/test01")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://example.com"


def test_redirect_not_found(client, seed_data):
    response = client.get("/nonexistent")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_redirect_inactive(client, seed_data):
    response = client.get("/dead01")
    assert response.status_code == 410
    assert "error" in response.get_json()


def test_list_urls(client, seed_data):
    response = client.get("/urls")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_click_count_increments(client, seed_data):
    # NOTE: this test requires two changes not yet in place:
    #   1. Add `click_count = IntegerField(default=0)` to ShortenedURL
    #   2. In the GET /<short_code> route, do:
    #      ShortenedURL.update(click_count=ShortenedURL.click_count + 1)
    #          .where(ShortenedURL.short_code == short_code).execute()
    client.get("/test01", follow_redirects=False)
    client.get("/test01", follow_redirects=False)

    url = ShortenedURL.get(ShortenedURL.short_code == "test01")
    assert url.click_count == 2


def test_metrics(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.get_json()
    assert "uptime_seconds" in data
    assert "database_status" in data

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


def test_shorten_with_title(client, seed_data):
    response = client.post("/shorten", json={"url": "https://titled.com", "title": "My Title"})
    assert response.status_code == 201
    data = response.get_json()
    assert data["title"] == "My Title"


def test_list_urls_filter_active(client, seed_data):
    response = client.get("/urls?active=true")
    assert response.status_code == 200
    urls = response.get_json()
    assert all(u["is_active"] for u in urls)


def test_list_urls_filter_inactive(client, seed_data):
    response = client.get("/urls?active=false")
    assert response.status_code == 200
    urls = response.get_json()
    assert all(not u["is_active"] for u in urls)


def test_get_url_by_id(client, seed_data):
    url_id = seed_data["active_url"].id
    response = client.get(f"/urls/{url_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["short_code"] == "test01"


def test_get_url_by_id_not_found(client, seed_data):
    response = client.get("/urls/99999")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_update_url(client, seed_data):
    url_id = seed_data["active_url"].id
    response = client.put(f"/urls/{url_id}", json={"title": "Updated"})
    assert response.status_code == 200
    assert response.get_json()["title"] == "Updated"


def test_update_url_not_found(client, seed_data):
    response = client.put("/urls/99999", json={"title": "Ghost"})
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_delete_url(client, seed_data):
    url_id = seed_data["active_url"].id
    response = client.delete(f"/urls/{url_id}")
    assert response.status_code == 200
    assert response.get_json() == {"message": "URL deleted"}

    url = ShortenedURL.get_by_id(url_id)
    assert url.is_active is False


def test_delete_url_not_found(client, seed_data):
    response = client.delete("/urls/99999")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_shorten_invalid_json(client, seed_data):
    response = client.post("/shorten", data="not-json", content_type="text/plain")
    assert response.status_code == 400
    assert response.get_json() == {"error": "URL is required"}


def test_error_handlers(client):
    response = client.put("/health")
    assert response.status_code == 405
    assert "error" in response.get_json()

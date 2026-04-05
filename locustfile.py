import random
import uuid

from locust import HttpUser, between, task

# Short codes sampled from seeds/urls.csv
SEED_SHORT_CODES = [
    "d1hixo",
    "8qyY0V",
    "PhuYte",
    "Wxz5xV",
    "ZP4ONl",
    "R4sdJX",
    "RC3FHS",
    "lboudL",
    "zYwFAR",
    "dgq3FF",
]


class URLShortenerUser(HttpUser):
    wait_time = between(1, 3)

    @task(1)
    def shorten_url(self):
        self.client.post(
            "/shorten",
            json={"url": f"https://example.com/{uuid.uuid4().hex}"},
        )

    @task(3)
    def redirect_url(self):
        short_code = random.choice(SEED_SHORT_CODES)
        self.client.get(f"/{short_code}", allow_redirects=False)

    @task(1)
    def list_urls(self):
        self.client.get("/urls")

    @task(1)
    def health_check(self):
        self.client.get("/health")

"""Редирект /go: логирование клика, sub_id, отказы."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.redirect import attach_sub_id, build_router
from api.redirect_targets import RedirectTarget, load_redirect_targets
from tracking.click import Click, InvalidClickError
from tracking.sqlite_log import SqliteClickLog
from tracking.sub_id import build_sub_id, sanitize


class MemoryClickLog:
    """Журнал в памяти — реализация того же порта, что и SqliteClickLog."""

    def __init__(self) -> None:
        self.clicks: list[Click] = []

    def record(self, click: Click) -> None:
        self.clicks.append(click)

    def count(self) -> int:
        return len(self.clicks)


@pytest.fixture
def log() -> MemoryClickLog:
    return MemoryClickLog()


@pytest.fixture
def client(log: MemoryClickLog, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    load_redirect_targets.cache_clear()
    monkeypatch.setattr(
        "api.redirect.load_redirect_targets",
        lambda: {
            "station_test_shop": RedirectTarget(
                url="https://rozetka.com.ua/p123/", source="rozetka.com.ua"
            ),
            "with_query_shop": RedirectTarget(
                url="https://example.com/p?ref=x", source="example.com"
            ),
        },
    )
    app = FastAPI()
    app.include_router(build_router(log))
    return TestClient(app)


def test_click_is_logged_before_redirect(client: TestClient, log: MemoryClickLog) -> None:
    response = client.get("/go/station_test_shop", follow_redirects=False)
    assert response.status_code == 302
    assert log.count() == 1
    assert log.clicks[0].offer_id == "station_test_shop"
    assert log.clicks[0].source == "rozetka.com.ua"


def test_sub_id_is_attached_to_target_url(client: TestClient) -> None:
    response = client.get(
        "/go/station_test_shop?scenario=abc123&position=2", follow_redirects=False
    )
    location = response.headers["location"]
    assert location.startswith("https://rozetka.com.ua/p123/?")
    assert "aff_sub=abc123" in location
    assert "%3A2%3A" in location or ":2:" in location


def test_existing_query_params_are_preserved(client: TestClient) -> None:
    response = client.get("/go/with_query_shop", follow_redirects=False)
    location = response.headers["location"]
    assert "ref=x" in location
    assert "aff_sub=" in location


def test_unknown_offer_is_404_and_logs_nothing(
    client: TestClient, log: MemoryClickLog
) -> None:
    """Клик без цели не записывается — иначе CTR завышается на мёртвых ссылках."""
    response = client.get("/go/does_not_exist", follow_redirects=False)
    assert response.status_code == 404
    assert log.count() == 0


def test_kit_offer_has_no_single_target(client: TestClient) -> None:
    """Кит — две покупки, одной целевой страницы у него нет (ADR-035)."""
    response = client.get("/go/kit__inv_a__bat_b", follow_redirects=False)
    assert response.status_code == 404


def test_sub_id_format_and_sanitizing() -> None:
    click = Click(
        offer_id="x", source="Rozetka.COM.ua", scenario_hash="AB 12/34", position=3
    )
    sub_id = build_sub_id(click)
    parts = sub_id.split(":")
    assert parts[0] == "ab_12_34"
    assert parts[1] == "rozetka_com_ua"
    assert parts[2] == "3"
    assert len(sub_id) <= 100


def test_sanitize_never_returns_empty() -> None:
    assert sanitize("///") == "na"


def test_click_rejects_invalid_input() -> None:
    with pytest.raises(InvalidClickError):
        Click(offer_id="", source="s", scenario_hash="h", position=0)
    with pytest.raises(InvalidClickError):
        Click(offer_id="o", source="s", scenario_hash="h", position=-1)


def test_click_ids_are_unique() -> None:
    made = {Click(offer_id="o", source="s", scenario_hash="h", position=0).click_id
            for _ in range(50)}
    assert len(made) == 50


def test_attach_sub_id_keeps_path_and_scheme() -> None:
    result = attach_sub_id("https://a.ua/path/", "s1")
    assert result == "https://a.ua/path/?aff_sub=s1"


def test_sqlite_log_persists_and_counts(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "clicks.db"
    log = SqliteClickLog(db)
    log.record(Click(offer_id="o1", source="s", scenario_hash="h", position=1))
    log.record(Click(offer_id="o2", source="s", scenario_hash="h", position=2))
    assert log.count() == 2
    assert SqliteClickLog(db).count() == 2, "журнал должен переживать перезапуск"


def test_sqlite_log_rejects_duplicate_click_id(tmp_path: Path) -> None:
    log = SqliteClickLog(tmp_path / "clicks.db")
    click = Click(offer_id="o", source="s", scenario_hash="h", position=0)
    log.record(click)
    with pytest.raises(Exception):
        log.record(click)


def test_redirect_response_carries_noindex_header(client: TestClient) -> None:
    response = client.get("/go/station_test_shop", follow_redirects=False)
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


def test_robots_txt_disallows_go() -> None:
    from fastapi.testclient import TestClient as RootClient

    from api.app import app as root_app

    response = RootClient(root_app).get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow: /go/" in response.text

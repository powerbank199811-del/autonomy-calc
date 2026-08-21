"""Редирект /go/{offer_id}: логирование клика и уход на партнёрскую ссылку.

Порядок операций жёсткий: записать клик, затем отдать 302. Обратный порядок
невозможен — после редиректа обработчик уже не выполняется. Если запись в
журнал упала, пользователь получает 500 и мы об этом узнаём. Молча увести
человека на маркетплейс, потеряв атрибуцию, хуже: комиссию за такой переход
никто не заплатит, а мы даже не будем знать, что он был.
"""

from urllib.parse import urlencode, urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from api.redirect_targets import load_redirect_targets
from tracking.click import Click
from tracking.port import ClickLog
from tracking.sub_id import build_sub_id

router = APIRouter()

#: Имя query-параметра для sub_id. У каждой сети своё; здесь дефолт
#: AliExpress Portals. Для SalesDoubler/Sellaction меняется в фазе 2 —
#: это и есть место, где адаптер источника вмешается в ссылку.
SUB_ID_PARAM = "aff_sub"


def attach_sub_id(url: str, sub_id: str, param: str = SUB_ID_PARAM) -> str:
    """Добавляет sub_id в query, сохраняя уже имеющиеся параметры."""
    parts = urlparse(url)
    query = parts.query
    extra = urlencode({param: sub_id})
    merged = f"{query}&{extra}" if query else extra
    return urlunparse(parts._replace(query=merged))


def build_router(click_log: ClickLog) -> APIRouter:
    """Собирает роутер с конкретной реализацией журнала.

    Журнал передаётся снаружи, а не импортируется внутри: это то, ради чего
    заведён порт ClickLog. Тест подставляет журнал в памяти, продакшен —
    SQLite, фаза 4 — PostgreSQL, и обработчик остаётся тем же.
    """
    local = APIRouter()

    @local.get("/go/{offer_id}")
    def go(
        offer_id: str,
        scenario: str = Query(default="direct"),
        position: int = Query(default=0, ge=0),
    ) -> RedirectResponse:
        targets = load_redirect_targets()
        target = targets.get(offer_id)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail=f"нет партнёрской ссылки для оффера '{offer_id}'",
            )

        click = Click(
            offer_id=offer_id,
            source=target.source,
            scenario_hash=scenario,
            position=position,
        )
        click_log.record(click)

        return RedirectResponse(
            url=attach_sub_id(target.url, build_sub_id(click)), status_code=302
        )

    return local

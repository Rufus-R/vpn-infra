"""Клиент API мастер-панели 3x-ui. См. docs/commercial/bot.md, раздел 'Интеграция с API Panel'.

КРИТИЧНО: update/{email} ВСЕГДА полностью заменяет строку клиента (full-replace, не patch) —
подтверждено контролируемым тестом 04.10.2026 (частичный update обнулил limitIp/totalGB/
expiryTime и перевёл enable в False). Поэтому:
  - для продления срока/трафика использовать bulk_adjust(), НЕ update_client_safe()
  - если изменение поля из update неизбежно — только через update_client_safe()
    (get + merge + полная отправка), никогда напрямую частичным телом
"""
from __future__ import annotations
import httpx
from app.config import PANEL_API_BASE, PANEL_API_TOKEN, PANEL_API_VERIFY_TLS


class PanelApiError(RuntimeError):
    pass


class PanelApiClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=PANEL_API_BASE,
            headers={"Authorization": f"Bearer {PANEL_API_TOKEN}"},
            verify=PANEL_API_VERIFY_TLS,
            timeout=15.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, path: str, **kwargs) -> dict:
        resp = await self._client.request(method, path, **kwargs)
        resp.raise_for_status()  # сетевой/авторизационный уровень
        data = resp.json()
        if not data.get("success", False):
            raise PanelApiError(f"{path}: {data.get('msg')!r}")
        return data

    async def add_client(self, *, email: str, limit_ip: int, total_gb: int,
                          expiry_time_ms: int, inbound_ids: list[int],
                          tg_id: int = 0, comment: str = "") -> dict:
        payload = {
            "client": {
                "email": email,
                "tgId": tg_id,
                "limitIp": limit_ip,
                "totalGB": total_gb,
                "expiryTime": expiry_time_ms,
                "enable": True,
                "comment": comment,
            },
            "inboundIds": inbound_ids,
        }
        return await self._call("POST", "/clients/add", json=payload)

    async def get_client(self, email: str) -> dict:
        data = await self._call("GET", f"/clients/get/{email}")
        return data["obj"]

    async def bulk_adjust(self, emails: list[str], *, add_days: int | None = None,
                           add_bytes: int | None = None) -> dict:
        payload: dict = {"emails": emails}
        if add_days is not None:
            payload["addDays"] = add_days
        if add_bytes is not None:
            payload["addBytes"] = add_bytes
        return await self._call("POST", "/clients/bulkAdjust", json=payload)

    async def update_client_safe(self, email: str, **changes) -> dict:
        """Безопасное частичное обновление: GET текущего клиента -> merge -> отправка
        ПОЛНОГО набора полей. НЕ вызывать update/{email} с частичным телом напрямую."""
        current = await self.get_client(email)
        client = current["client"]
        client.update(changes)
        return await self._call("POST", f"/clients/update/{email}", json=client)

    async def sub_links(self, sub_id: str) -> dict:
        return await self._call("GET", f"/clients/subLinks/{sub_id}")

"""
Cliente del Core API para las herramientas (INV-32, T10).

Reenvía el `Authorization` del usuario y el `X-Request-Id` en cada llamada: el
agente no tiene credenciales propias (INV-30, criterio 6) y el Core API decide
los permisos (D13). Cada falla se convierte en `ErrorHerramienta`, que el bucle
devuelve al modelo como dato para que la explique (criterio 5):

- el estado HTTP y el `detail` del Core API, que ya viene en español
  («Solo puede consultar su sucursal (PRINCIPAL)»); si `detail` es la lista de
  la validación de FastAPI, se unen sus `msg` (C11);
- 504 si la llamada pasa de `CORE_API_TIMEOUT_S`, y 503 si no hay conexión.
"""
import logging
from typing import Any

import httpx

from core.config import Settings

# httpx registra en INFO la URL completa de cada petición, y la de las
# herramientas lleva lo que escribió el usuario (`busqueda=…`): nunca al
# registro (Ley 1581, DoD 5). Lo encontró la prueba del registro (INV-32).
for _nombre in ("httpx", "httpcore"):
    logging.getLogger(_nombre).setLevel(logging.WARNING)


class ErrorHerramienta(Exception):
    def __init__(self, status: int, mensaje: str):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje

    def para_modelo(self) -> dict:
        return {"error": {"status": self.status, "mensaje": self.mensaje}}


def _mensaje(r: httpx.Response) -> str:
    try:
        detalle = r.json().get("detail", r.text)
    except (ValueError, AttributeError):
        return r.text[:300] or f"El Core API respondió {r.status_code}"
    if isinstance(detalle, list):
        return "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detalle)
    return str(detalle)


class ClienteCoreAPI:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._timeout = settings.CORE_API_TIMEOUT_S
        self._http = httpx.AsyncClient(
            base_url=settings.CORE_API_URL,
            timeout=httpx.Timeout(settings.CORE_API_TIMEOUT_S, connect=5.0),
            transport=transport,
        )

    async def pedir(self, metodo: str, ruta: str, autorizacion: str, request_id: str,
                    params: dict | None = None, cuerpo: dict | None = None) -> Any:
        # Sin los filtros vacíos: el Core API los trataría como un valor
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            r = await self._http.request(metodo, ruta, params=params, json=cuerpo,
                                         headers={"Authorization": autorizacion, "X-Request-Id": request_id})
        except httpx.TimeoutException as exc:
            raise ErrorHerramienta(504, f"El Core API no respondió en {self._timeout:.0f} s") from exc
        except httpx.TransportError as exc:
            raise ErrorHerramienta(503, "El Core API no está disponible") from exc
        if r.status_code != 200:
            raise ErrorHerramienta(r.status_code, _mensaje(r))
        return r.json()

    async def cerrar(self) -> None:
        await self._http.aclose()

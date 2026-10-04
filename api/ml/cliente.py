"""
InventAI/o — Cliente del Core API hacia ml_service (INV-23)
Llama a /api/health, /api/compras y /api/transferencias y traduce sus
errores a los del Core API (docs/INV-23-requerimientos.md, "Errores").
INV-25 reutiliza este cliente.
"""
from functools import lru_cache
from typing import Optional

import httpx
from fastapi import HTTPException, status

from core.config import get_settings


class ClienteML:
    def __init__(self, base_url: str, timeout: float, transport: Optional[httpx.BaseTransport] = None):
        self.timeout = timeout
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def salud(self) -> dict:
        """GET /api/health. Exige la bodega conectada, una foto cargada y las
        versiones de políticas: son la clave de la caché."""
        body = self._llamar("GET", "/api/health")
        if "politicas" not in body or "fecha_inventario" not in body:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                                "ML Service sin fecha_inventario ni politicas en /api/health: versión anterior a INV-23")
        if body.get("status") != "ok":
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ML Service degradado: sin conexión a la bodega")
        if not body["fecha_inventario"]:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ML Service sin foto de inventario cargada")
        return body

    def compras(self) -> dict:
        """POST /api/compras del catálogo completo, con el detalle por sucursal."""
        return self._llamar("POST", "/api/compras", {"incluir_detalle": True})

    def transferencias(self) -> dict:
        """POST /api/transferencias del catálogo completo, con el balance."""
        return self._llamar("POST", "/api/transferencias", {"incluir_balance": True})

    def predecir(self, cuerpo: dict) -> dict:
        """POST /api/predict (INV-25). Sus 404 y 422 son errores de la petición
        (producto o sucursal desconocidos, historia insuficiente, sucursal no
        física) y pasan tal cual, con su detail (R5)."""
        return self._llamar("POST", "/api/predict", cuerpo, pasar=(404, 422))

    def _llamar(self, metodo: str, ruta: str, cuerpo: Optional[dict] = None, pasar: tuple = ()) -> dict:
        try:
            r = self._http.request(metodo, ruta, json=cuerpo)
        except httpx.TimeoutException:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, f"ML Service no respondió en {self.timeout:g} s")
        except httpx.TransportError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ML Service no disponible")
        if r.status_code == 200:
            return r.json()
        if r.status_code in pasar:
            # el detail tal cual: texto, o la lista de errores de validación
            try:
                body = r.json()
            except ValueError:
                body = None
            original = body.get("detail") if isinstance(body, dict) else None
            raise HTTPException(r.status_code, original if original is not None else r.text[:500])
        detalle = _detalle(r)
        if r.status_code == 409:
            raise HTTPException(status.HTTP_409_CONFLICT, detalle)
        if r.status_code == 503:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"ML Service: {detalle}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"ML Service respondió {r.status_code}: {detalle}")


def _detalle(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        body = None
    detalle = body.get("detail") if isinstance(body, dict) else None
    return detalle if isinstance(detalle, str) else r.text[:500]


@lru_cache
def get_cliente_ml() -> ClienteML:
    settings = get_settings()
    return ClienteML(settings.ML_SERVICE_URL, settings.ML_SERVICE_TIMEOUT_SEGUNDOS)

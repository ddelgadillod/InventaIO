#!/usr/bin/env python3
"""
InventAI/o — Pruebas de humo del staging (INV-34, B20 y CA 7).

Recorre la aplicación desplegada por su dominio, como un navegador:

  https       HTTP redirige a HTTPS y el certificado es válido para el dominio
  app         / sirve la aplicación con HSTS y CSP
  salud       /api/health trae la versión y el commit esperados
  login       la cuenta de humo entra
  datos       /api/consulta/sucursales trae sucursales
  alertas_ml  /api/alertas/ml responde (el componente inteligente, INV-28)
  chat        Vera responde por /api/chat/message y el flujo termina en `done`
  404         una ruta del api que no existe da 404

Solo usa la biblioteca estándar y corre con el Python de Amazon Linux 2023 (3.9), sin instalar nada.
Imprime el nombre, el resultado y el tiempo de cada prueba, nunca datos de la bodega ni la clave. Sale con
0 si todas pasan y con 1 si alguna falla. Lo corre scripts/desplegar_staging.sh después de cada despliegue:

    python3 scripts/humo_staging.py https://staging.inventaio.<dominio> \\
        --credenciales /opt/inventaio/estado/humo.env --version 2.1.0 --commit a1b2c3d

El archivo de credenciales tiene HUMO_EMAIL=… y HUMO_CLAVE=…, uno por línea; lo escribe
`desplegar_staging.sh --configurar-humo`. --ca agrega una CA de confianza (la interna de Caddy en la prueba
local) y --omitir salta pruebas por nombre.
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

PRUEBAS = ["https", "app", "salud", "login", "datos", "alertas_ml", "chat", "404"]
PREGUNTA = "¿Cuántas sucursales hay?"
TIMEOUT_S = 30
TIMEOUT_LENTO_S = 135          # las alertas con IA en frío y el chat: lo mismo que espera Nginx


class Falla(Exception):
    """Una prueba que no pasó, con un motivo sin datos."""


class SinRedirecciones(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None             # la redirección llega como HTTPError, para revisarla


class Cliente:
    def __init__(self, base: str, ca: str | None):
        self.base = base.rstrip("/")
        contexto = ssl.create_default_context()
        if ca:
            contexto.load_verify_locations(ca)
        https = urllib.request.HTTPSHandler(context=contexto)
        self._abrir = urllib.request.build_opener(https, SinRedirecciones).open
        self.token: str | None = None

    def pedir(self, metodo: str, url: str, cuerpo: dict | None = None, timeout: float = TIMEOUT_S,
              flujo: bool = False):
        """(código, cabeceras, cuerpo); con flujo=True, la respuesta abierta en lugar del cuerpo."""
        if not url.startswith("http"):
            url = self.base + url
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        peticion = urllib.request.Request(url, data=datos, method=metodo)
        if datos is not None:
            peticion.add_header("Content-Type", "application/json")
        if self.token:
            peticion.add_header("Authorization", f"Bearer {self.token}")
        try:
            r = self._abrir(peticion, timeout=timeout)
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except urllib.error.URLError as e:
            motivo = e.reason
            if isinstance(motivo, ssl.SSLCertVerificationError):
                raise Falla(f"certificado no válido ({motivo.verify_message})") from None
            raise Falla(f"sin conexión ({motivo})") from None
        if flujo:
            return r.status, r.headers, r
        with r:
            return r.status, r.headers, r.read()

    def json(self, metodo: str, ruta: str, cuerpo: dict | None = None, timeout: float = TIMEOUT_S) -> dict:
        codigo, _, contenido = self.pedir(metodo, ruta, cuerpo, timeout)
        if codigo != 200:
            raise Falla(f"{ruta} respondió {codigo}")
        return json.loads(contenido)


def leer_credenciales(ruta: str) -> tuple[str, str]:
    valores = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            clave, _, valor = linea.rstrip("\n").partition("=")
            valores[clave.strip()] = valor
    if not valores.get("HUMO_EMAIL") or not valores.get("HUMO_CLAVE"):
        raise SystemExit(f"{ruta}: faltan HUMO_EMAIL o HUMO_CLAVE (desplegar_staging.sh --configurar-humo)")
    return valores["HUMO_EMAIL"], valores["HUMO_CLAVE"]


def prueba_https(c: Cliente, args) -> str:
    host = urlparse(c.base).hostname
    codigo, cabeceras, _ = c.pedir("GET", args.url_http or f"http://{host}/")
    destino = cabeceras.get("Location", "")
    if codigo not in (301, 302, 307, 308) or not destino.startswith(f"https://{host}"):
        raise Falla(f"HTTP respondió {codigo} sin redirigir a https://{host}")
    c.pedir("HEAD", "/")        # valida el certificado: un error de TLS sale como Falla
    return f"{codigo} hacia HTTPS, certificado válido"


def prueba_app(c: Cliente, args) -> str:
    codigo, cabeceras, contenido = c.pedir("GET", "/")
    if codigo != 200 or b'<div id="root">' not in contenido:
        raise Falla(f"/ respondió {codigo} sin la aplicación")
    faltan = [h for h in ("Strict-Transport-Security", "Content-Security-Policy") if not cabeceras.get(h)]
    if faltan:
        raise Falla("faltan " + " y ".join(faltan))
    return "HSTS y CSP"


def prueba_salud(c: Cliente, args) -> str:
    salud = c.json("GET", "/api/health")
    if args.version and salud.get("version") != args.version:
        raise Falla(f"versión {salud.get('version')}, se esperaba {args.version}")
    if args.commit and salud.get("commit") != args.commit[:7]:
        raise Falla(f"commit {salud.get('commit') or '(vacío)'}, se esperaba {args.commit[:7]}")
    return f"v{salud.get('version')} · {salud.get('commit') or 'sin commit'}"


def prueba_login(c: Cliente, args) -> str:
    email, clave = leer_credenciales(args.credenciales)
    codigo, _, contenido = c.pedir("POST", "/api/auth/login", {"email": email, "password": clave})
    if codigo != 200:
        raise Falla(f"login respondió {codigo}")
    c.token = json.loads(contenido)["access_token"]
    return "token recibido"


def prueba_datos(c: Cliente, args) -> str:
    total = c.json("GET", "/api/consulta/sucursales").get("total", 0)
    if not total:
        raise Falla("sin sucursales: ¿falta restaurar la bodega?")
    return f"{total} ubicaciones"


def prueba_alertas_ml(c: Cliente, args) -> str:
    alertas = c.json("GET", "/api/alertas/ml?page=1&page_size=1", timeout=TIMEOUT_LENTO_S)
    if "resumen" not in alertas:
        raise Falla("respuesta sin resumen")
    return "con pronóstico" if alertas.get("fecha_pronostico") else "sin pronóstico"


def prueba_chat(c: Cliente, args) -> str:
    cuerpo = {"mensajes": [{"rol": "usuario", "texto": PREGUNTA}]}
    codigo, _, r = c.pedir("POST", "/api/chat/message", cuerpo, timeout=TIMEOUT_LENTO_S, flujo=True)
    if codigo != 200:
        raise Falla(f"chat respondió {codigo}")
    eventos, inicio, primero, nombre = [], time.monotonic(), None, None
    with r:
        for linea in r:
            linea = linea.decode("utf-8").rstrip("\n")
            if linea.startswith("event: "):
                nombre = linea[len("event: "):]
                eventos.append(nombre)
                if nombre == "token" and primero is None:
                    primero = time.monotonic() - inicio
            elif linea.startswith("data: ") and nombre == "error":
                raise Falla(f"evento error: {json.loads(linea[len('data: '):]).get('codigo')}")
            elif linea.startswith("data: ") and nombre == "done":
                break
    if "done" not in eventos:
        raise Falla("el flujo terminó sin done")
    if "token" not in eventos:
        raise Falla("done sin texto de respuesta")
    return f"primer texto a los {primero:.1f} s, {len(eventos)} eventos"


def prueba_404(c: Cliente, args) -> str:
    codigo, cabeceras, _ = c.pedir("GET", "/api/no-existe")
    if codigo != 404 or "json" not in cabeceras.get("Content-Type", ""):
        raise Falla(f"/api/no-existe respondió {codigo}")
    return "404 del api"


def main() -> int:
    parser = argparse.ArgumentParser(description="Pruebas de humo del staging (INV-34)")
    parser.add_argument("url", help="https://<dominio>")
    parser.add_argument("--credenciales", help="archivo con HUMO_EMAIL y HUMO_CLAVE")
    parser.add_argument("--version", help="la versión que debe devolver /api/health")
    parser.add_argument("--commit", help="el commit que debe devolver /api/health")
    parser.add_argument("--ca", help="CA adicional de confianza (prueba local con la CA interna de Caddy)")
    parser.add_argument("--url-http", help="URL HTTP para la redirección (por defecto http://<dominio>/)")
    parser.add_argument("--omitir", action="append", default=[], choices=PRUEBAS, help="repetible")
    args = parser.parse_args()
    if not args.credenciales and not {"login", "datos", "alertas_ml", "chat"} <= set(args.omitir):
        parser.error("falta --credenciales (o --omitir login, datos, alertas_ml y chat)")

    c = Cliente(args.url, args.ca)
    fallas = 0
    activas = [p for p in PRUEBAS if p not in args.omitir]
    for nombre in PRUEBAS:
        if nombre not in activas:
            print(f"  {nombre:<11} omitida")
            continue
        if c.token is None and nombre in ("datos", "alertas_ml", "chat") and "login" not in args.omitir:
            print(f"  {nombre:<11} FALLA  (sin login)")
            fallas += 1
            continue
        inicio = time.monotonic()
        try:
            detalle = globals()[f"prueba_{nombre}"](c, args)
            print(f"  {nombre:<11} ok     {time.monotonic() - inicio:5.1f} s  {detalle}")
        except (Falla, OSError, ValueError, KeyError) as e:
            print(f"  {nombre:<11} FALLA  {time.monotonic() - inicio:5.1f} s  {e}")
            fallas += 1
    print(f"Humo: {len(activas) - fallas} de {len(activas)} pruebas en ok")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())

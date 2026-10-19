"""
Pregunta al agente (INV-32) como uno de los usuarios de prueba y muestra los
eventos SSE del contrato v1: las herramientas, las tablas, la respuesta a
medida que se genera y las cifras de `done`.

Necesita solo httpx. La clave de los usuarios de prueba (api/scripts/seed_usuarios.py)
va en INVENTAIO_CLAVE_PRUEBA.

Con el agente corriendo en el equipo (cd nlp_agent && uvicorn main:app --port 8002):
    python scripts/preguntar_agente.py --rol gerente "¿Qué productos están críticos en GLORIETA?"
    python scripts/preguntar_agente.py --rol admin_sucursal --sucursal "LA 21" "¿Y en GLORIETA?"

Dentro del contenedor, porque el 8002 no se publica:
    docker compose exec -T -e INVENTAIO_CLAVE_PRUEBA nlp-agent python - --agente http://localhost:8002 \\
        --core-api http://api:8000 --rol gerente "¿Cuánto arroz hay?" < scripts/preguntar_agente.py

--crudo muestra cada evento tal cual llega (útil para INV-35). --turnos agrega
turnos anteriores ("usuario:…" o "agente:…") para probar una conversación.
"""
import argparse
import json
import os
import sys
import uuid

import httpx

USUARIOS = {
    ("gerente", None): "gerente@inventaio.co",
    ("admin_bodega", None): "bodega@inventaio.co",
    ("admin_sucursal", "PRINCIPAL"): "admin.principal@inventaio.co",
    ("admin_sucursal", "LA 21"): "admin.norte@inventaio.co",
    ("admin_sucursal", "GLORIETA"): "admin.sur@inventaio.co",
}


def token(core_api: str, rol: str, sucursal: str | None) -> str:
    clave = os.environ.get("INVENTAIO_CLAVE_PRUEBA")
    if not clave:
        sys.exit("Define INVENTAIO_CLAVE_PRUEBA con la clave de los usuarios de prueba")
    email = USUARIOS.get((rol, sucursal if rol == "admin_sucursal" else None))
    if email is None:
        sys.exit("Rol o sucursal desconocidos. admin_sucursal necesita --sucursal PRINCIPAL, \"LA 21\" o GLORIETA")
    r = httpx.post(f"{core_api}/api/auth/login", json={"email": email, "password": clave}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"No se pudo iniciar sesión con {email}: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def eventos(respuesta: httpx.Response):
    """Lector de SSE: un evento por bloque separado por una línea vacía; ignora los comentarios («: ping»)."""
    nombre, datos = None, []
    for linea in respuesta.iter_lines():
        if linea.startswith(":"):
            continue
        if not linea:
            if nombre:
                yield nombre, json.loads("\n".join(datos))
            nombre, datos = None, []
        elif linea.startswith("event: "):
            nombre = linea[7:]
        elif linea.startswith("data: "):
            datos.append(linea[6:])


def tabla(d: dict) -> str:
    columnas = d["columnas"]
    filas = [[str(f.get(c["clave"], "")) for c in columnas] for f in d["filas"]]
    anchos = [min(max(len(c["titulo"]), *(len(f[i]) for f in filas)), 48) for i, c in enumerate(columnas)]
    corta = lambda t, n: t if len(t) <= n else t[: n - 1] + "…"  # noqa: E731
    lineas = ["  " + " | ".join(corta(c["titulo"], anchos[i]).ljust(anchos[i]) for i, c in enumerate(columnas))]
    lineas.append("  " + "-+-".join("-" * a for a in anchos))
    lineas += ["  " + " | ".join(corta(v, anchos[i]).ljust(anchos[i]) for i, v in enumerate(f)) for f in filas]
    pie = f"  {d['mostrando']} de {d['total']} · datos al {d['fecha_dato']}"
    return f"\n[{d['forma']}] {d['titulo']}\n" + "\n".join(lineas) + "\n" + pie


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("pregunta")
    a.add_argument("--rol", required=True, choices=["gerente", "admin_bodega", "admin_sucursal"])
    a.add_argument("--sucursal", choices=["PRINCIPAL", "LA 21", "GLORIETA"])
    a.add_argument("--agente", default=os.environ.get("AGENTE_URL", "http://localhost:8002"))
    a.add_argument("--core-api", default=os.environ.get("CORE_API_URL", "http://localhost:8000"))
    a.add_argument("--turnos", nargs="*", default=[], help='turnos anteriores: "usuario:texto" o "agente:texto"')
    a.add_argument("--crudo", action="store_true", help="cada evento tal cual llega")
    args = a.parse_args(argv)

    mensajes = [{"rol": t.split(":", 1)[0], "texto": t.split(":", 1)[1]} for t in args.turnos]
    mensajes.append({"rol": "usuario", "texto": args.pregunta})
    cabeceras = {"Authorization": f"Bearer {token(args.core_api, args.rol, args.sucursal)}", "X-Request-Id": uuid.uuid4().hex}
    with httpx.stream("POST", f"{args.agente}/chat", json={"mensajes": mensajes}, headers=cabeceras, timeout=150) as r:
        if r.status_code != 200:
            r.read()
            print(f"HTTP {r.status_code}: {r.text}")
            return 1
        en_texto = False
        for nombre, d in eventos(r):
            if args.crudo:
                print(f"{nombre}: {json.dumps(d, ensure_ascii=False)}")
                continue
            if nombre != "token" and en_texto:
                print()
                en_texto = False
            if nombre == "meta":
                print(f"· {d['modelo']} · prompt {d['version_prompt']} · request_id {d['request_id']}")
            elif nombre == "tool" and d["estado"] == "inicio":
                print(f"[herramienta {d['id']}] {d['etiqueta']}" + (" (puede tardar hasta 40 s)" if d["lenta"] else ""))
            elif nombre == "tool":
                print(f"[herramienta {d['id']}] {d['nombre']}: {d['estado']} en {d['ms']} ms" + (f" (código {d['codigo']})" if d["codigo"] else ""))
            elif nombre == "data":
                print(tabla(d))
            elif nombre == "token":
                if not en_texto:
                    print("\nRespuesta:")
                    en_texto = True
                print(d["texto"], end="", flush=True)
            elif nombre == "done":
                print(f"\n· {d['rondas']} rondas · tokens {d['tokens_prompt']} (ronda mayor) / {d['tokens_respuesta']} · "
                      f"{d['ms_total'] / 1000:.1f} s (modelo {d['ms_modelo'] / 1000:.1f} s, herramientas {d['ms_herramientas'] / 1000:.1f} s)"
                      f" · datos al {', '.join(d['fechas_datos']) or '—'}")
            elif nombre == "error":
                print(f"\nERROR {d['codigo']}: {d['mensaje']}")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

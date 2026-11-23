#!/usr/bin/env python3
"""
InventAI/o — Sube un volcado de la bodega al bucket de traslado de staging (INV-34, B2 y B11).

Sube dw.dump, dw.dump.sha256 y huella.txt de la carpeta que dejó scripts/bd/volcar.sh a
s3://BUCKET/volcados/<nombre de la carpeta>/, con su suma SHA-256 para que S3 rechace un
archivo que llegue cambiado. huella-detalle.txt no se sube.

Usa el perfil inventaio-volcados de ~/.aws (un usuario de IAM que solo puede escribir en
volcados/; ver la sección 7 de docs/INV-34-requerimientos.md). Solo necesita botocore, que
ya está en el entorno del agente. No imprime contenido: solo las claves que sube.

    python scripts/bd/subir_volcado.py ~/inventaio-volcados/20261112-0930 --bucket inventaio-staging-xxxx
    python scripts/bd/subir_volcado.py CARPETA --bucket B --simular   # comprueba, sin subir
"""
import argparse
import base64
import hashlib
import sys
from pathlib import Path

ARCHIVOS = ("dw.dump", "dw.dump.sha256", "huella.txt")


def sha256(datos: bytes) -> bytes:
    return hashlib.sha256(datos).digest()


def comprobar(carpeta: Path) -> str | None:
    """Devuelve el problema de la carpeta, o None si se puede subir."""
    faltan = [nombre for nombre in ARCHIVOS if not (carpeta / nombre).is_file()]
    if faltan:
        return f"faltan {', '.join(faltan)} en {carpeta}"
    esperado = (carpeta / "dw.dump.sha256").read_text(encoding="utf-8").split()[0]
    if sha256((carpeta / "dw.dump").read_bytes()).hex() != esperado:
        return "dw.dump no coincide con dw.dump.sha256"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sube un volcado de dw al bucket de traslado.")
    parser.add_argument("carpeta", type=Path, help="la carpeta que dejó volcar.sh")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--perfil", default="inventaio-volcados")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--prefijo", default="volcados")
    parser.add_argument("--simular", action="store_true", help="comprueba la carpeta y muestra las claves, sin subir")
    args = parser.parse_args(argv)

    carpeta = args.carpeta.expanduser().resolve()
    problema = comprobar(carpeta)
    if problema:
        print(f"ERROR: {problema}", file=sys.stderr)
        return 2

    claves = [f"{args.prefijo}/{carpeta.name}/{nombre}" for nombre in ARCHIVOS]
    if args.simular:
        for clave in claves:
            print(f"subiría s3://{args.bucket}/{clave}")
        return 0

    # Se importa aquí para que --simular funcione sin botocore
    import botocore.session
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        s3 = botocore.session.Session(profile=args.perfil).create_client("s3", region_name=args.region)
        for nombre, clave in zip(ARCHIVOS, claves):
            datos = (carpeta / nombre).read_bytes()
            s3.put_object(
                Bucket=args.bucket,
                Key=clave,
                Body=datos,
                ChecksumSHA256=base64.b64encode(sha256(datos)).decode("ascii"),
            )
            print(f"s3://{args.bucket}/{clave}")
    except (BotoCoreError, ClientError) as error:
        # El mensaje de botocore no incluye la llave; sí el perfil, el bucket o el código de AWS
        print(f"ERROR: no se pudo subir: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

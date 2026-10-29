FROM python:3.11-slim

WORKDIR /app

# LightGBM necesita OpenMP (libgomp) y la imagen slim no lo trae. De paso, los
# parches de seguridad de Debian publicados después de la imagen base.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Con la red lenta: pip 26 retoma una descarga que se corta a mitad
# (--resume-retries; la 24.0 de la imagen base no puede), espera hasta 120 s
# por respuesta y reintenta las conexiones. La caché de BuildKit guarda lo ya
# descargado para el siguiente build (no queda dentro de la imagen).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 "pip==26.2.1" \
    && pip install --timeout 120 --retries 10 --resume-retries 10 -r requirements.txt

# Producción: sin pruebas (.dockerignore), sin root y con healthcheck (INV-24, D8)
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MODELOS_DIR=/app/models
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
# Sin pip, setuptools ni wheel: la app no los usa al correr y traen vulnerabilidades
# propias (setuptools y las librerías que pip lleva dentro)
RUN pip uninstall -y setuptools wheel \
    && python -m pip uninstall -y pip

COPY . .

# Los modelos van dentro de la imagen (D9). Llegan como el contexto adicional
# `models` (docker-compose.yml, docker-compose.verify.yml e images.yml lo pasan):
# la raíz del repositorio nunca es contexto de build. El build falla si un modelo
# no coincide con su SHA-256.
COPY --from=models . /app/models
RUN cd /app/models && sha256sum -c --quiet SHA256SUMS

USER app
EXPOSE 8001
# /api/health responde 200 aunque la bodega no esté ("degradado"): el contenedor
# está sano si el servicio y los modelos cargaron. La imagen slim no trae curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/health', timeout=4)"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]

FROM python:3.11-slim

WORKDIR /app

# Los parches de seguridad de Debian publicados después de la imagen base
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Con la red lenta: pip 26 retoma una descarga que se corta a mitad
# (--resume-retries), espera hasta 120 s por respuesta y reintenta las
# conexiones. La caché de BuildKit no queda dentro de la imagen.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 "pip==26.2.1" \
    && pip install --timeout 120 --retries 10 --resume-retries 10 -r requirements.txt

# Producción como las demás imágenes (INV-24, D8; INV-30, criterio 1): sin pruebas
# (.dockerignore), sin root, sin --reload y con healthcheck
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
# Sin pip, setuptools ni wheel: la app no los usa al correr
RUN pip uninstall -y setuptools wheel \
    && python -m pip uninstall -y pip

COPY . .

USER app
# Solo en la red interna: ni el compose ni Nginx publican este puerto (INV-36)
EXPOSE 8002
# /health responde aunque Ollama no esté: el contenedor está sano si el proceso
# vive. Que el modelo esté listo lo dice /ready. La imagen slim no trae curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=4)"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]

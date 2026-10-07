FROM python:3.11-slim AS deps

WORKDIR /app

COPY requirements.txt .
# Con la red lenta: pip 26 retoma una descarga que se corta a mitad
# (--resume-retries; la 24.0 de la imagen base no puede), espera hasta 120 s
# por respuesta y reintenta las conexiones. La caché de BuildKit guarda lo ya
# descargado para el siguiente build (no queda dentro de la imagen).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 "pip==26.2.1" \
    && pip install --timeout 120 --retries 10 --resume-retries 10 -r requirements.txt

# Desarrollo (el target de docker-compose.yml): agrega pytest, ruff y pip-audit
# para correr las pruebas dentro del contenedor. requirements-dev.txt está en la
# raíz del repositorio y llega como el contexto adicional `raiz`; BuildKit solo
# transfiere ese archivo, no el resto de la raíz.
FROM deps AS dev
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,from=raiz,source=requirements-dev.txt,target=/tmp/requirements-dev.txt \
    pip install --timeout 120 --retries 10 --resume-retries 10 -r /tmp/requirements-dev.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Producción (la imagen por defecto): sin herramientas de prueba
FROM deps AS prod
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

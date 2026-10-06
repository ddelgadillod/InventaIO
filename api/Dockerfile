FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# Con la red lenta: pip 26 retoma una descarga que se corta a mitad
# (--resume-retries; la 24.0 de la imagen base no puede), espera hasta 120 s
# por respuesta y reintenta las conexiones. La caché de BuildKit guarda lo ya
# descargado para el siguiente build (no queda dentro de la imagen).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 "pip==26.2.1" \
    && pip install --timeout 120 --retries 10 --resume-retries 10 -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# InventAI/o — El frontend compilado y servido por Nginx (ver frontend/README.md).
# En desarrollo se sigue usando `npm run dev`; esta imagen es la de producción.

# Debian y no Alpine: Vite 8 (Rolldown) y Tailwind 4 traen binarios nativos y el
# package-lock.json se generó en Linux con glibc
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
# Con la red lenta, como el pip del Core API: más reintentos y esperas largas.
# La caché de BuildKit guarda lo ya descargado para el siguiente build
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund --fetch-retries=6 --fetch-retry-mintimeout=20000 \
      --fetch-retry-maxtimeout=120000 --fetch-timeout=600000
COPY . .
RUN npm run build

# Nginx sin root (INV-24, D8): la variante oficial "unprivileged" corre como el
# usuario nginx (101) y escucha en 8080, porque sin root no puede abrir el 80.
# El host publica el 80 y el 443 hacia el 8080 y el 8443 (contrato con INV-34)
FROM nginxinc/nginx-unprivileged:1.30-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1

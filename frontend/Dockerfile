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

FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

#!/usr/bin/env bash
# InventAI/o — Prueba el streaming del chat por Nginx (INV-36, criterio 5).
#
# Levanta un Core API falso que envía 5 eventos SSE, uno por segundo, el Nginx
# del repositorio (frontend/nginx.conf con nginx/chat-sse.conf) delante de él y,
# de control, el mismo Nginx sin el bloque del chat y con text/event-stream en
# gzip_types: lo que acumula el flujo es comprimirlo (C3). Comprueba que:
#   1. por /api/chat/, cada evento llega cuando se envía (el primero en menos de
#      0,5 s y el último después de 3,5 s), no todos juntos al final;
#   2. por /api/chat/, aunque el navegador acepte gzip, la respuesta no se comprime;
#   3. el control acumula los eventos: el primer byte llega después de 3,5 s;
#   4. /api/ sigue igual: nginx -t y un JSON grande sale comprimido.
# Necesita Docker y las imágenes ya descargadas (las de probar_nginx_timeout.sh).
# Tarda menos de un minuto. Desde la raíz del repositorio:
#   bash scripts/probar_nginx_streaming.sh
set -euo pipefail

RAIZ=$(cd "$(dirname "$0")/.." && pwd)
RED=inventaio-prueba-sse
NGINX=nginxinc/nginx-unprivileged:1.30-alpine   # la base de frontend/Dockerfile
TMP=""

limpiar_docker() {
  docker rm -f inv-sse-api inv-sse-nginx inv-sse-control >/dev/null 2>&1 || true
  docker network rm "$RED" >/dev/null 2>&1 || true
}
trap 'limpiar_docker; rm -rf "$TMP"' EXIT
limpiar_docker
TMP=$(mktemp -d)

SERVIDOR='
import http.server, json, time
class CoreFalso(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for i in range(5):
            datos = json.dumps({"texto": "fragmento %d" % i})
            self.wfile.write(("event: token\ndata: " + datos + "\n\n").encode())
            self.wfile.flush()
            time.sleep(1)
    def do_GET(self):
        cuerpo = json.dumps({"items": [{"producto": f"PRODUCTO {i}", "stock": i} for i in range(80)]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)
    def log_message(self, *args):
        pass
http.server.ThreadingHTTPServer(("", 8000), CoreFalso).serve_forever()
'

# El control: sin el bloque del chat (/api/chat/ cae en /api/) y comprimiendo los eventos
sed -E '/include \/etc\/nginx\/snippets\/chat-sse.conf;/d; s#(gzip_types .*);#\1 text/event-stream;#' \
  "$RAIZ/frontend/nginx.conf" > "$TMP/control.conf"

docker network create "$RED" >/dev/null
docker run -d --name inv-sse-api --network "$RED" --network-alias api python:3.11-slim python -c "$SERVIDOR" >/dev/null
docker run -d --name inv-sse-nginx --network "$RED" -p 18082:8080 \
  -v "$RAIZ/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$RAIZ/frontend/nginx/chat-sse.conf:/etc/nginx/snippets/chat-sse.conf:ro" "$NGINX" >/dev/null
docker run -d --name inv-sse-control --network "$RED" -p 18083:8080 \
  -v "$TMP/control.conf:/etc/nginx/conf.d/default.conf:ro" "$NGINX" >/dev/null

docker exec inv-sse-nginx nginx -t 2>&1 | tail -1
for i in $(seq 1 30); do
  curl -sf "http://localhost:18082/api/json" >/dev/null 2>&1 && break
  sleep 1
done

# Mide cuándo llega cada evento (o, si viene comprimido, el primer byte)
MEDIR='
import http.client, json, sys, time
puerto = int(sys.argv[1])
c = http.client.HTTPConnection("localhost", puerto, timeout=30)
inicio = time.monotonic()
c.request("POST", "/api/chat/message", body="{}", headers={"Accept-Encoding": "gzip", "Content-Type": "application/json"})
r = c.getresponse()
llegadas, primer_byte, texto = [], None, b""
while True:
    trozo = r.read1(65536)
    if not trozo:
        break
    t = round(time.monotonic() - inicio, 2)
    primer_byte = primer_byte if primer_byte is not None else t
    texto += trozo
    llegadas += [t] * trozo.count(b"event: ")
print(json.dumps({"llegadas": llegadas, "primer_byte": primer_byte, "encoding": r.getheader("Content-Encoding")}))
'
python3 -c "$MEDIR" 18082 > "$TMP/chat.json" &
python3 -c "$MEDIR" 18083 > "$TMP/control.json" &
wait

FALLAS=0
revisar() {   # nombre, condición en Python sobre d (el JSON de la medición)
  if python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if ($3) else 1)" "$2"; then
    echo "OK    $1"
  else
    echo "FALLA $1: $(cat "$2")"; FALLAS=$((FALLAS + 1))
  fi
}
revisar "1. /api/chat/: los 5 eventos llegan uno por segundo" "$TMP/chat.json" \
  'len(d["llegadas"]) == 5 and d["llegadas"][0] < 0.5 and d["llegadas"][-1] > 3.5'
revisar "2. /api/chat/: sin comprimir aunque el navegador acepte gzip" "$TMP/chat.json" 'd["encoding"] is None'
revisar "3. control (sin el bloque y con gzip): el primer byte llega al final" "$TMP/control.json" \
  'd["primer_byte"] > 3.5 and d["encoding"] == "gzip"'

ENC=$(curl -s -o /dev/null -w '%{content_type} %{size_download}' -H 'Accept-Encoding: gzip' "http://localhost:18082/api/json")
CABECERA=$(curl -s -D - -o /dev/null -H 'Accept-Encoding: gzip' "http://localhost:18082/api/json" | tr -d '\r' | grep -i '^content-encoding' || true)
if [[ "$CABECERA" == *gzip* ]]; then
  echo "OK    4. /api/: un JSON grande sale comprimido ($ENC bytes)"
else
  echo "FALLA 4. /api/: el JSON no salió comprimido ($CABECERA)"; FALLAS=$((FALLAS + 1))
fi

echo "Llegadas por /api/chat/: $(cat "$TMP/chat.json")"
echo "Control: $(cat "$TMP/control.json")"
[ "$FALLAS" -eq 0 ] && echo "Todo bien" || { echo "$FALLAS comprobaciones fallaron"; exit 1; }

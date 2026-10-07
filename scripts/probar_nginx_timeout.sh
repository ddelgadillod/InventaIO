#!/usr/bin/env bash
# InventAI/o — Prueba los tiempos de espera de frontend/nginx.conf.
#
# Levanta un Core API falso que responde cuando se le pide (/api/lento?s=N),
# el Nginx del repositorio delante de él y, de control, el mismo Nginx con los
# tiempos por defecto. Comprueba que:
#   1. una respuesta que tarda 70 s pasa (Nginx, por defecto, corta a los 60 s);
#   2. la misma respuesta, con los tiempos por defecto, da 504 a los 60 s;
#   3. una que tarda 140 s da 504 a los 135 s.
# Necesita Docker y tarda unos dos minutos y medio. Desde la raíz del repositorio:
#   bash scripts/probar_nginx_timeout.sh
set -euo pipefail

RAIZ=$(cd "$(dirname "$0")/.." && pwd)
RED=inventaio-prueba-nginx
NGINX=nginx:1.28-alpine
TMP=""

# Quita lo de una corrida anterior que se haya cortado, y lo de esta al salir
limpiar_docker() {
  docker rm -f inv-prueba-api inv-prueba-nginx inv-prueba-defecto >/dev/null 2>&1 || true
  docker network rm "$RED" >/dev/null 2>&1 || true
}
trap 'limpiar_docker; rm -rf "$TMP"' EXIT
limpiar_docker
TMP=$(mktemp -d)

SERVIDOR='
import http.server, json, time, urllib.parse
class Lento(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        consulta = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        time.sleep(float(consulta.get("s", ["0"])[0]))
        cuerpo = json.dumps({"ok": True}).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
        except BrokenPipeError:
            pass
    def log_message(self, *args):
        pass
http.server.ThreadingHTTPServer(("", 8000), Lento).serve_forever()
'

# El control: la misma configuración sin los tiempos de espera de lectura y escritura
sed -E '/proxy_(send|read)_timeout/d' "$RAIZ/frontend/nginx.conf" > "$TMP/defecto.conf"

docker network create "$RED" >/dev/null
docker run -d --name inv-prueba-api --network "$RED" --network-alias api python:3.11-slim python -c "$SERVIDOR" >/dev/null
docker run -d --name inv-prueba-nginx --network "$RED" -p 18080:80 \
  -v "$RAIZ/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" "$NGINX" >/dev/null
docker run -d --name inv-prueba-defecto --network "$RED" -p 18081:80 \
  -v "$TMP/defecto.conf:/etc/nginx/conf.d/default.conf:ro" "$NGINX" >/dev/null

docker exec inv-prueba-nginx nginx -t 2>&1 | tail -1
for i in $(seq 1 30); do
  curl -sf "http://localhost:18080/api/lento?s=0" >/dev/null 2>&1 && break
  sleep 1
done

pedir() { curl -s -o /dev/null -m 200 -w '%{http_code} %{time_total}\n' "http://localhost:$1/api/lento?s=$2"; }
echo "Pidiendo en paralelo (unos 135 s)…"
pedir 18080 70 > "$TMP/a" &
pedir 18081 70 > "$TMP/b" &
pedir 18080 140 > "$TMP/c" &
wait

fallas=0
revisar() { # descripción, archivo, código esperado, segundos mínimos, segundos máximos
  read -r codigo segundos < "$2"
  if [ "$codigo" = "$3" ] && awk -v s="$segundos" -v a="$4" -v b="$5" 'BEGIN { exit !(s >= a && s <= b) }'; then
    echo "OK     $1: $codigo en ${segundos%.*} s"
  else
    echo "FALLA  $1: se esperaba $3 entre $4 y $5 s; llegó $codigo en ${segundos%.*} s"
    fallas=1
  fi
}
revisar "70 s con frontend/nginx.conf" "$TMP/a" 200 69 80
revisar "70 s con los tiempos por defecto" "$TMP/b" 504 59 65
revisar "140 s con frontend/nginx.conf" "$TMP/c" 504 134 140
exit $fallas

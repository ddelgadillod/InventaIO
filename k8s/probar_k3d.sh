#!/usr/bin/env bash
# InventAI/o — Prueba de los manifiestos en un clúster k3s de verdad (k3d), en local y en el CI (fase 3 de
# docs/INFRA-k3s-serverless-requerimientos.md).
#
# Crea el clúster «inventaio-prueba» como quedará la máquina: k3s sin Traefik, con ServiceLB y con las reglas de red
# de k3s. Carga las imágenes inventaio-*:ci, despliega k8s/overlays/ci con las funciones de scripts/desplegar.sh y
# comprueba:
#   - Pod Security «restricted»: todo arranca sin root y con la raíz de solo lectura, y un pod privilegiado se rechaza
#   - Postgres crea el esquema al arrancar y la migración se repite sin cambios
#   - Caddy: 403 sin la cabecera secreta de origen; con ella, el humo (https, app, salud y 404)
#   - la IP del visitante (la última de X-Forwarded-For, como la agrega CloudFront; IPv4 e IPv6) llega al Core API, y
#     la que inventa el visitante no
#   - las reglas de red: lo permitido conecta y lo demás no
#   - los scripts de la base dentro del clúster (BD_POD): volcar con app, restaurar y validar
#   - Redis conserva sus datos después de reiniciarse (AOF)
# Al final muestra la memoria de cada pod, para elegir el tamaño de la máquina.
#
#   bash k8s/probar_k3d.sh                # con las imágenes inventaio-*:ci ya construidas (el CI las construye)
#   bash k8s/probar_k3d.sh --construir    # las construye antes con docker-compose.verify.yml
#   bash k8s/probar_k3d.sh --conservar    # deja el clúster al terminar, para mirarlo con kubectl
# No toca ~/.kube/config. Sale con 0 si todo pasó y con 1 si algo falló.
set -uo pipefail

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CLUSTER=${CLUSTER:-inventaio-prueba}
# La misma versión que instalará despliegue/preparar_k3s.sh en la máquina (fase 4): el canal estable de k3s
K3S_IMAGEN=${K3S_IMAGEN:-rancher/k3s:v1.37.2-k3s1}
HTTPS=${PUERTO_HTTPS:-18443}
HTTP=${PUERTO_HTTP:-18080}
NS=inventaio
SERVICIOS=(api ml-service nlp-agent web)
BEDROCK=bedrock-runtime.us-east-2.amazonaws.com

construir=0
conservar=0
for opcion in "$@"; do
    case $opcion in
        --construir) construir=1 ;;
        --conservar) conservar=1 ;;
        *) echo "uso: probar_k3d.sh [--construir] [--conservar]"; exit 2 ;;
    esac
done
for herramienta in docker k3d kubectl curl python3; do
    command -v "$herramienta" >/dev/null || { echo "Falta $herramienta"; exit 2; }
done

TMP=$(mktemp -d)
export KUBECONFIG=$TMP/kubeconfig
bien=0; mal=0
fila() { local n=${#1}; printf '  %s%*s %s\n' "$1" $((n < 50 ? 50 - n : 0)) '' "$2"; }
ok() { fila "$1" "OK${2:+ · $2}"; bien=$((bien + 1)); }
falla() { fila "$1" "FALLA${2:+ · $2}"; mal=$((mal + 1)); }
dato() { fila "$1" "$2"; }
seccion() { printf '\n%s\n' "$1"; }
k() { kubectl -n "$NS" "$@"; }
aleatorio() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }

diagnostico() {
    kubectl get namespace "$NS" >/dev/null 2>&1 || return 0
    printf '\n── Diagnóstico\n'
    kubectl get pods -A -o wide
    k get events --sort-by=.lastTimestamp | tail -n 30
    local pod
    for pod in $(k get pods -o name); do
        if [[ $(k get "$pod" -o jsonpath='{.status.containerStatuses[*].ready}') != *false* ]]; then continue; fi
        printf '\n── %s\n' "$pod"
        k describe "$pod" | tail -n 25
        k logs "$pod" --all-containers --tail=40 || true
    done
}

limpiar() {
    local rc=$?
    if [[ $rc -ne 0 || $mal -gt 0 ]]; then diagnostico; fi
    if [[ $conservar == 1 ]]; then
        printf '\nEl clúster sigue: export KUBECONFIG=%s · para borrarlo: k3d cluster delete %s\n' "$KUBECONFIG" "$CLUSTER"
    else
        k3d cluster delete "$CLUSTER" >/dev/null 2>&1 || true
        rm -rf "$TMP"
    fi
}
trap limpiar EXIT

# ── Imágenes ────────────────────────────────────────

if [[ $construir == 1 ]]; then
    echo "Construyendo las imágenes con docker-compose.verify.yml…"
    docker compose -f "$RAIZ/docker-compose.verify.yml" build >"$TMP/construir.log" 2>&1 \
        || { tail -n 30 "$TMP/construir.log"; echo "No se pudieron construir las imágenes"; exit 1; }
    for s in "${SERVICIOS[@]}"; do docker tag "inventaio-$s:verify" "inventaio-$s:ci"; done
fi
imagenes=()
for s in "${SERVICIOS[@]}"; do
    docker image inspect "inventaio-$s:ci" >/dev/null 2>&1 \
        || { echo "Falta la imagen inventaio-$s:ci: corre con --construir"; exit 2; }
    imagenes+=("inventaio-$s:ci")
done

echo "InventAI/o · prueba de k8s/ en k3d · $K3S_IMAGEN · $(date '+%Y-%m-%d %H:%M')"

# ── Manifiestos ─────────────────────────────────────

# kubeconform no lo ve: el namespace de la base no alcanza lo que agrega cada variante (pasó con Postgres y RDS)
seccion "Las tres variantes, todo en el espacio de nombres $NS"
python3 -c 'import yaml' 2>/dev/null || { echo "Falta PyYAML para python3"; exit 2; }
for variante in staging produccion ci; do
    if ! fuera=$(kubectl kustomize "$RAIZ/k8s/overlays/$variante" | python3 -c '
import sys, yaml
print(" ".join(d["kind"] + "/" + d["metadata"]["name"] for d in yaml.safe_load_all(sys.stdin)
               if d and d["kind"] != "Namespace" and d["metadata"].get("namespace") != sys.argv[1]))' "$NS"); then
        falla "Variante $variante" "no se genera"
    elif [[ -n $fuera ]]; then
        falla "Variante $variante" "fuera de $NS: $fuera"
    else
        ok "Variante $variante"
    fi
done

# ── Clúster ─────────────────────────────────────────
seccion "Clúster como el de la máquina"
k3d cluster delete "$CLUSTER" >/dev/null 2>&1 || true      # lo que haya quedado de una corrida anterior
if ! k3d cluster create "$CLUSTER" --image "$K3S_IMAGEN" --servers 1 --agents 0 \
        --k3s-arg '--disable=traefik@server:0' \
        --port "$HTTPS:443@loadbalancer" --port "$HTTP:80@loadbalancer" \
        --kubeconfig-update-default=false --kubeconfig-switch-context=false --wait --timeout 180s \
        >"$TMP/k3d.log" 2>&1; then
    tail -n 20 "$TMP/k3d.log"
    falla "Crear el clúster"
    exit 1
fi
k3d kubeconfig get "$CLUSTER" > "$KUBECONFIG"
for d in coredns local-path-provisioner metrics-server; do
    kubectl -n kube-system rollout status "deployment/$d" --timeout=180s >/dev/null 2>&1 \
        || { falla "Sistema del clúster" "$d no quedó listo"; exit 1; }
done
ok "k3s sin Traefik, con ServiceLB y reglas de red" "$(kubectl version -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["serverVersion"]["gitVersion"])')"
dns=$(kubectl -n kube-system get service kube-dns -o jsonpath='{.spec.clusterIP}')
if [[ $dns == 10.43.0.10 ]]; then
    ok "DNS del clúster en 10.43.0.10" "el que usa k8s/base/nginx/upstream.conf"
else
    falla "DNS del clúster" "$dns: cambia k8s/base/nginx/upstream.conf"
fi
if k3d image import --cluster "$CLUSTER" "${imagenes[@]}" >"$TMP/importar.log" 2>&1; then
    ok "Imágenes cargadas" "${imagenes[*]}"
else
    tail -n 20 "$TMP/importar.log"
    falla "Cargar las imágenes"
    exit 1
fi

# ── Despliegue, con las funciones de scripts/desplegar.sh ──

seccion "Despliegue como scripts/desplegar.sh, la primera vez"
DIR=$RAIZ
AMBIENTE=staging
KUBECTL=kubectl
ORIGEN=$(aleatorio)
# En lugar de Parameter Store: secretos nuevos en cada corrida
secreto() { if [[ $1 == origen-secreto ]]; then echo "$ORIGEN"; else aleatorio; fi; }
fallar() { falla "$*"; exit 1; }
paso() { :; }
# shellcheck source=/dev/null
source <(sed -n -e '/^preparar_cluster() {/,/^}/p' -e '/^migrar() {/,/^}/p' -e '/^hay_base_lista() {/,/^}/p' \
    -e '/^esperar_servicios() {/,/^}/p' "$RAIZ/scripts/desplegar.sh")
for funcion in preparar_cluster migrar hay_base_lista esperar_servicios; do
    declare -F "$funcion" >/dev/null || fallar "scripts/desplegar.sh ya no tiene la función $funcion"
done

preparar_cluster
ok "Espacio de nombres, Secret y esquema"
if hay_base_lista; then falla "Base lista antes de desplegar" "en un clúster nuevo no debería"; fi
if ! salida=$(kubectl apply -k "$RAIZ/k8s/overlays/ci" 2>&1); then
    echo "$salida" | tail -n 20
    fallar "kubectl apply -k k8s/overlays/ci"
fi
if grep -q 'would violate PodSecurity' <<<"$salida"; then
    falla "Pod Security «restricted»" "$(grep -m 1 'would violate PodSecurity' <<<"$salida")"
else
    ok "Pod Security «restricted»" "ninguna advertencia al aplicar"
fi
inicio=$SECONDS
if esperar_servicios >"$TMP/esperar.log" 2>&1; then
    ok "Postgres, Redis, Caddy y los cuatro servicios" "listos en $((SECONDS - inicio)) s"
else
    tail -n 5 "$TMP/esperar.log"
    fallar "Los servicios no quedaron listos"
fi
if migrar sha-ci0001 >"$TMP/migrar.log" 2>&1 && migrar sha-ci0002 >>"$TMP/migrar.log" 2>&1; then
    ok "Migración dos veces seguidas" "init.sql se repite sin errores"
else
    tail -n 20 "$TMP/migrar.log"
    falla "Migración"
fi
if hay_base_lista; then ok "hay_base_lista ve la base"; else falla "hay_base_lista no ve la base"; fi

# ── Seguridad de los pods ───────────────────────────

seccion "Sin root y con la raíz de solo lectura"
for objetivo in deployment/api deployment/ml-service deployment/nlp-agent deployment/web deployment/redis \
        deployment/caddy pod/postgres-0; do
    uid=$(k exec "$objetivo" -- id -u 2>/dev/null)
    if k exec "$objetivo" -- touch /prueba-de-escritura >/dev/null 2>&1; then escribe=sí; else escribe=no; fi
    if [[ -n $uid && $uid != 0 && $escribe == no ]]; then
        ok "${objetivo#*/}" "uid $uid, no escribe en /"
    else
        falla "${objetivo#*/}" "uid ${uid:-?}, escribe en /: $escribe"
    fi
done
privilegiado='{"apiVersion": "v1", "spec": {"containers": [{"name": "privilegiado", "image": "postgres:16-alpine",
    "securityContext": {"privileged": true}}]}}'
salida=$(k run privilegiado --image=postgres:16-alpine --restart=Never --dry-run=server --overrides="$privilegiado" 2>&1)
if grep -q 'violates PodSecurity' <<<"$salida"; then
    ok "Un pod privilegiado" "Pod Security lo rechaza"
else
    falla "Un pod privilegiado" "se aceptó"
fi

# ── Caddy y el humo ─────────────────────────────────

seccion "Caddy: la cabecera secreta de origen y el humo"
for _ in $(seq 30); do
    k exec deployment/caddy -- cat /data/caddy/pki/authorities/local/root.crt > "$TMP/ca.crt" 2>/dev/null \
        && [[ -s $TMP/ca.crt ]] && break
    sleep 2
done
[[ -s $TMP/ca.crt ]] || falla "La CA interna de Caddy" "no apareció en /data/caddy"
URL=https://localhost:$HTTPS
pedir() { curl -s --cacert "$TMP/ca.crt" --max-time 30 -o /dev/null -w '%{http_code}' "$@"; }
codigo=$(pedir "$URL/api/health")
if [[ $codigo == 403 ]]; then ok "Sin la cabecera" "403"; else falla "Sin la cabecera" "$codigo (se esperaba 403)"; fi
codigo=$(pedir -H 'X-Origen-Secreto: otra-cosa' "$URL/api/health")
if [[ $codigo == 403 ]]; then ok "Con otra cabecera" "403"; else falla "Con otra cabecera" "$codigo (se esperaba 403)"; fi
# Sin cuenta, bodega ni Bedrock en k3d: el humo corre lo que no los necesita
if python3 "$RAIZ/scripts/humo_staging.py" "$URL" --ca "$TMP/ca.crt" --url-http "http://localhost:$HTTP/" \
        --cabecera "X-Origen-Secreto: $ORIGEN" --version "$(tr -d '[:space:]' < "$RAIZ/VERSION")" \
        --omitir login --omitir datos --omitir alertas_ml --omitir compras --omitir chat >"$TMP/humo.log" 2>&1; then
    ok "Humo con la cabecera" "$(tail -n 1 "$TMP/humo.log")"
else
    sed 's/^/    /' "$TMP/humo.log"
    falla "Humo con la cabecera"
fi

# ── La IP del visitante ─────────────────────────────

seccion "La IP del visitante llega al Core API (contadores del login en Redis)"
# login <IP del visitante>: un login fallido como lo manda CloudFront: la X-Forwarded-For que inventó el visitante,
# con la IP real agregada al final. Devuelve el código
login() {
    pedir -X POST "$URL/api/auth/login" -H "X-Origen-Secreto: $ORIGEN" -H "X-Forwarded-For: 198.51.100.9, $1" \
        -H 'Content-Type: application/json' -d '{"email": "nadie@ejemplo.com", "password": "no-es-la-clave"}'
}
codigo4=$(login 203.0.113.7)
codigo6=$(login 2001:db8::7)
if [[ $codigo4 == 401 && $codigo6 == 401 ]]; then
    ok "Login con una cuenta que no existe" "401: el Core API consultó Postgres"
else
    falla "Login con una cuenta que no existe" "$codigo4 y $codigo6 (se esperaba 401)"
fi
claves=$(k exec deployment/redis -- redis-cli --scan --pattern 'login:fallos:ip:*' 2>/dev/null | sort | tr '\n' ' ')
if [[ $claves == *"login:fallos:ip:203.0.113.7 "* ]]; then ok "IPv4 del visitante" "203.0.113.7"; else falla "IPv4 del visitante" "Redis tiene: ${claves:-nada}"; fi
if [[ $claves == *"login:fallos:ip:2001:db8::7 "* ]]; then ok "IPv6 del visitante" "2001:db8::7"; else falla "IPv6 del visitante" "Redis tiene: ${claves:-nada}"; fi
if [[ -n $claves && $claves != *198.51.100.9* && $claves != *"ip:10.42."* ]]; then
    ok "Ni la X-Forwarded-For falsa ni una IP interna"
else
    falla "Ni la X-Forwarded-For falsa ni una IP interna" "Redis tiene: ${claves:-nada}"
fi

# ── Reglas de red ───────────────────────────────────

seccion "Reglas de red: lo permitido conecta y lo demás no"
k apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: intruso
  labels:
    app.kubernetes.io/name: intruso
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 70
    runAsGroup: 70
    seccompProfile: {type: RuntimeDefault}
  containers:
    - name: intruso
      image: postgres:16-alpine
      command: [sleep, "900"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: {drop: [ALL]}
EOF
k wait --for=condition=Ready pod/intruso --timeout=120s >/dev/null || falla "El pod intruso no arrancó"
# Python en las imágenes de Python; nc de busybox en las de alpine. Responde conecta, no-conecta o sin-dns
PY_CONECTA='import socket, sys
nombre, puerto = sys.argv[1], int(sys.argv[2])
try:
    ip = socket.getaddrinfo(nombre, puerto, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
except OSError:
    print("sin-dns"); sys.exit()
try:
    socket.create_connection((ip, puerto), 3).close(); print("conecta")
except OSError:
    print("no-conecta")'
SH_CONECTA='nslookup "$1" >/dev/null 2>&1 || { echo sin-dns; exit; }
if nc -z -w 3 "$1" "$2" 2>/dev/null; then echo conecta; else echo no-conecta; fi'
conecta() {
    case $1 in
        api|ml-service|nlp-agent) k exec "deployment/$1" -- python -c "$PY_CONECTA" "$2" "$3" 2>/dev/null ;;
        intruso) k exec pod/intruso -- sh -c "$SH_CONECTA" sh "$2" "$3" 2>/dev/null ;;
        *) k exec "deployment/$1" -- sh -c "$SH_CONECTA" sh "$2" "$3" 2>/dev/null ;;
    esac
}
# red <conecta|no-conecta> <origen> <destino> <puerto>; los servicios del clúster, por su nombre completo
red() {
    local destino=$3 resultado
    [[ $destino == *.* ]] || destino=$destino.$NS.svc.cluster.local
    resultado=$(conecta "$2" "$destino" "$4")
    if [[ $resultado == "$1" ]]; then
        ok "$2 → $3:$4" "$([[ $1 == conecta ]] && echo conecta || echo bloqueado)"
    else
        falla "$2 → $3:$4" "${resultado:-sin respuesta} (se esperaba $1)"
    fi
}
red conecta    caddy      web        8080
red no-conecta caddy      api        8000
red conecta    web        api        8000
red no-conecta web        postgres   5432
red conecta    api        postgres   5432
red conecta    api        redis      6379
red conecta    api        ml-service 8001
red conecta    api        nlp-agent  8002
red no-conecta api        "$BEDROCK" 443
red conecta    ml-service postgres   5432
red no-conecta ml-service redis      6379
red no-conecta ml-service "$BEDROCK" 443
red conecta    nlp-agent  api        8000
red no-conecta nlp-agent  postgres   5432
red conecta    nlp-agent  "$BEDROCK" 443
red no-conecta redis      api        8000
red no-conecta intruso    postgres   5432
red no-conecta intruso    api        8000
red no-conecta intruso    redis      6379
k delete pod intruso --wait=false >/dev/null 2>&1

# ── Scripts de la base dentro del clúster ───────────

seccion "Scripts de la base con BD_POD (scripts/bd/comun.sh)"
# El ciclo del traslado entre staging (volcar con app, restaurar y validar) dentro del clúster. La base de la prueba
# solo tiene el esquema, así que el volcado viaja vacío: lo que se prueba es el camino, no los datos (eso lo hace el
# job «Base de datos»). En una subcapa: herramientas_k8s pone su propio trap de salida, que borra el pod al terminar
if (
    set -e
    # shellcheck source=/dev/null
    source "$RAIZ/scripts/bd/comun.sh"
    herramientas_k8s "$RAIZ/k8s/plantillas/bd-herramientas.yaml"
    exigir_conexion
    pg_sql -A -t -c "SELECT string_agg(nspname, ',' ORDER BY nspname) FROM pg_namespace WHERE nspname IN ('app', 'dw')"
    INCLUIR_APP=1 bash "$RAIZ/scripts/bd/volcar.sh" "$TMP/volcado"
    bash "$RAIZ/scripts/bd/restaurar.sh" "$TMP/volcado"
    bash "$RAIZ/scripts/bd/validar.sh" "$TMP/volcado"
) >"$TMP/bd.log" 2>&1 && grep -qx 'app,dw' "$TMP/bd.log" && [[ -s $TMP/volcado/dw.dump && -s $TMP/volcado/app.dump ]]; then
    ok "Pod de herramientas, conexión y esquemas" "app y dw"
    ok "Volcar con app, restaurar y validar" "$(grep -m 1 '^PASÓ' "$TMP/bd.log")"
else
    sed 's/^/    /' "$TMP/bd.log" | tail -n 20
    falla "Scripts de la base con BD_POD"
fi

# ── Redis con AOF ───────────────────────────────────

seccion "Redis conserva sus datos al reiniciarse"
aof=$(k exec deployment/redis -- redis-cli CONFIG GET appendonly 2>/dev/null | tail -n 1)
k exec deployment/redis -- redis-cli SET prueba:aof sigue EX 900 >/dev/null 2>&1
sleep 2                                   # appendfsync everysec
k delete pod -l app.kubernetes.io/name=redis --wait=true >/dev/null 2>&1
k rollout status deployment/redis --timeout=120s >/dev/null 2>&1
valor=$(k exec deployment/redis -- redis-cli GET prueba:aof 2>/dev/null)
contadores=$(k exec deployment/redis -- redis-cli --scan --pattern 'login:fallos:*' 2>/dev/null | wc -l)
if [[ $aof == yes && $valor == sigue && $contadores -gt 0 ]]; then
    ok "Pod nuevo, mismos datos" "appendonly=yes; la llave de prueba y $contadores contadores del login"
else
    falla "Redis después de reiniciarse" "appendonly=${aof:-?}, llave=${valor:-perdida}, contadores=$contadores"
fi

# ── Memoria ─────────────────────────────────────────

seccion "Memoria de cada pod, para elegir el tamaño de la máquina"
for _ in $(seq 24); do kubectl top pods -n "$NS" >/dev/null 2>&1 && break; sleep 5; done
if kubectl top pods -n "$NS" --no-headers >"$TMP/top.txt" 2>/dev/null; then
    while read -r pod cpu memoria; do dato "$pod" "$memoria · CPU $cpu"; done < "$TMP/top.txt"
    dato "Total de los pods" "$(awk '{ sub(/Mi$/, "", $3); total += $3 } END { print total "Mi" }' "$TMP/top.txt")"
    read -r _ _ _ nodo_memoria nodo_porcentaje < <(kubectl top node --no-headers)
    dato "El nodo completo (con k3s)" "$nodo_memoria ($nodo_porcentaje de lo que ve el nodo)"
else
    dato "kubectl top" "sin métricas todavía"
fi

printf '\nResumen: %d OK · %d FALLA\n' "$bien" "$mal"
[[ $mal -eq 0 ]]

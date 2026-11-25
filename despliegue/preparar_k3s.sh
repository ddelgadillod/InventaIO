#!/usr/bin/env bash
# InventAI/o — Prepara una máquina Amazon Linux 2023 para correr la aplicación en k3s (plan de staging en k3s con
# servicios serverless, fase 4: docs/INFRA-k3s-serverless-requerimientos.md):
#   - 2 GB de swap, git, jq y tar;
#   - k3s fijado por versión y SHA-256: sin Traefik, con ServiceLB (publica Caddy en el 80 y el 443), cifrado de los
#     Secrets y registros de los contenedores con tope;
#   - el agente de CloudWatch, con la memoria y el disco que vigilan las alarmas de infra/;
#   - /opt/inventaio con el ambiente, y el kubeconfig de ec2-user, que corre scripts/desplegar.sh;
#   - en staging, el servicio que al encender se pone al día con develop (scripts/al_dia.sh).
#
# Lo corre el primer arranque de la máquina (user_data de infra/modulos/ambiente), como root, después de clonar el
# repositorio en /opt/inventaio/repo. Es idempotente: se puede repetir desde Session Manager sin cambiar lo que ya está:
#   sudo AMBIENTE=staging bash /opt/inventaio/repo/despliegue/preparar_k3s.sh
# El registro del primer arranque queda en /var/log/inventaio-preparar.log.
set -euo pipefail

# El canal estable de k3s al 24-nov-2026; la misma versión que prueba k8s/probar_k3d.sh
K3S_VERSION=v1.37.2+k3s1
K3S_SHA256=265b3ee6a3198ef14033c63ef46cbb32370d83795199fb6d1b01f21575eddbda
INSTALADOR_SHA256=ed01f89fd977bf20ac1516bbebf8370bf3ddbaa55dac8aba610956a4c78cc00b
USUARIO=${USUARIO:-ec2-user}
BASE=/opt/inventaio
AMBIENTE=${AMBIENTE:-}

fallar() { echo "ERROR: $*" >&2; exit 2; }
[[ $EUID -eq 0 ]] || fallar "córrelo con sudo"
[[ $AMBIENTE == staging || $AMBIENTE == produccion ]] || fallar "falta AMBIENTE=staging o AMBIENTE=produccion"

# descargar <url> <sha256> <destino>: solo deja el archivo si coincide con su suma
descargar() {
    curl -fsSL --retry 3 -o "$3.tmp" "$1"
    echo "$2  $3.tmp" | sha256sum -c --quiet \
        || { rm -f "$3.tmp"; fallar "la descarga de $1 no coincide con su SHA-256"; }
    mv "$3.tmp" "$3"
}

echo "== Paquetes"
dnf install -y -q git jq tar amazon-cloudwatch-agent

echo "== Swap de 2 GB"
# El swap es para el sistema: los pods no lo usan (kubelet con NoSwap). Si no está activo, se formatea aunque el
# archivo exista, porque puede venir de una corrida que se cortó
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
    [[ -f /swapfile ]] || fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap defaults 0 0' >> /etc/fstab
echo 'vm.swappiness=10' > /etc/sysctl.d/90-inventaio-swap.conf
sysctl -q --system

echo "== k3s $K3S_VERSION"
install -d -m 755 /etc/rancher/k3s
cat > /etc/rancher/k3s/config.yaml <<EOF
# InventAI/o (despliegue/preparar_k3s.sh). ServiceLB sigue encendido: publica Caddy (H15)
node-name: inventaio-$AMBIENTE
disable:
  - traefik
secrets-encryption: true
write-kubeconfig-mode: "0600"
kubelet-arg:
  - container-log-max-size=10Mi
  - container-log-max-files=3
  # Con el swap de la máquina el kubelet arranca igual; los pods no lo usan (NoSwap)
  - fail-swap-on=false
EOF
version_url=${K3S_VERSION/+/%2B}
if ! { [[ -x /usr/local/bin/k3s ]] && echo "$K3S_SHA256  /usr/local/bin/k3s" | sha256sum -c --quiet 2>/dev/null; }; then
    descargar "https://github.com/k3s-io/k3s/releases/download/$version_url/k3s" "$K3S_SHA256" /usr/local/bin/k3s
    chmod 755 /usr/local/bin/k3s
fi
# El instalador oficial de esa misma versión solo crea el servicio de systemd y los enlaces (kubectl, crictl): el
# binario ya está verificado. Amazon Linux 2023 trae SELinux en modo permisivo, así que no hace falta k3s-selinux
instalador=$(mktemp)
descargar "https://raw.githubusercontent.com/k3s-io/k3s/$version_url/install.sh" "$INSTALADOR_SHA256" "$instalador"
INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_VERSION=$K3S_VERSION INSTALL_K3S_SKIP_SELINUX_RPM=true \
    INSTALL_K3S_SELINUX_WARN=true sh "$instalador" >/dev/null
rm -f "$instalador"
for _ in $(seq 60); do
    [[ $(k3s kubectl get node "inventaio-$AMBIENTE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null) == True ]] && break
    sleep 5
done
[[ $(k3s kubectl get node "inventaio-$AMBIENTE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}') == True ]] \
    || fallar "el nodo de k3s no quedó listo en 5 minutos: journalctl -u k3s"

echo "== kubeconfig de $USUARIO"
install -d -o "$USUARIO" -g "$USUARIO" -m 700 "/home/$USUARIO/.kube"
install -o "$USUARIO" -g "$USUARIO" -m 600 /etc/rancher/k3s/k3s.yaml "/home/$USUARIO/.kube/config"
# El kubectl de k3s, sin KUBECONFIG, lee /etc/rancher/k3s/k3s.yaml (solo root) y no ~/.kube/config (H34). En las
# sesiones queda definido; los scripts lo definen por su cuenta
cat > /etc/profile.d/inventaio-kubeconfig.sh <<'FIN'
# InventAI/o (despliegue/preparar_k3s.sh): el kubectl de k3s usa la copia de cada usuario, si tiene una
if [ -z "${KUBECONFIG:-}" ] && [ -r "$HOME/.kube/config" ]; then export KUBECONFIG="$HOME/.kube/config"; fi
FIN

echo "== Agente de CloudWatch: memoria y disco"
# aggregation_dimensions publica además cada métrica solo con InstanceId, que es lo que miran las alarmas
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'EOF'
{
  "agent": { "metrics_collection_interval": 60 },
  "metrics": {
    "namespace": "CWAgent",
    "append_dimensions": { "InstanceId": "${aws:InstanceId}" },
    "aggregation_dimensions": [["InstanceId"]],
    "metrics_collected": {
      "mem": { "measurement": ["mem_used_percent"] },
      "disk": { "measurement": ["used_percent"], "resources": ["/"] }
    }
  }
}
EOF
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json >/dev/null

echo "== $BASE"
install -d -o "$USUARIO" -g "$USUARIO" -m 755 "$BASE" "$BASE/versiones"
install -d -o "$USUARIO" -g "$USUARIO" -m 700 "$BASE/estado"
echo "$AMBIENTE" > "$BASE/estado/ambiente"
chown "$USUARIO:$USUARIO" "$BASE/estado/ambiente"

if [[ $AMBIENTE == staging ]]; then
    # De noche está apagado (P16): al encender despliega el último commit de develop (scripts/al_dia.sh)
    echo "== Ponerse al día con develop al encender"
    install -m 644 "$(dirname "$0")/systemd/inventaio-al-dia.service" /etc/systemd/system/inventaio-al-dia.service
    systemctl daemon-reload
    systemctl enable inventaio-al-dia.service 2>/dev/null
fi

echo "== Listo"
echo "k3s: $(k3s --version | head -n 1)"
k3s kubectl get node -o wide --no-headers
echo "Memoria: $(free -m | awk '/^Mem:/ { print $7 " MB disponibles de " $2 }') · swap: $(free -m | awk '/^Swap:/ { print $2 " MB" }')"
echo "Sigue: como $USUARIO, bash $BASE/repo/scripts/desplegar.sh <tag> --primera-vez"

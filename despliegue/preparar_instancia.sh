#!/usr/bin/env bash
# InventAI/o — Prepara la instancia del staging (INV-34, B21): Docker, Compose fijado, git, 2 GB de swap y las
# carpetas de /opt/inventaio. Amazon Linux 2023, una sola vez, desde Session Manager (guía, §7):
#   sudo bash /opt/inventaio/repo/despliegue/preparar_instancia.sh
# Es idempotente: otra corrida no cambia lo que ya está. Al final muestra las versiones y prueba que Compose
# hable con el Docker de la distribución (riesgo de la §16 de los requerimientos).
set -euo pipefail

COMPOSE_VERSION=v5.6.1      # 21-oct-2026; la misma serie que el equipo de desarrollo
COMPOSE_SHA256=47737f4236e6d3ccea7291995203f8f018058783b4c3a9469119811a0b5db8c0
USUARIO=${USUARIO:-ec2-user}
PLUGIN=/usr/local/lib/docker/cli-plugins/docker-compose

[[ $EUID -eq 0 ]] || { echo "ERROR: córrelo con sudo" >&2; exit 2; }

echo "== Docker y git"
dnf install -y -q docker git
systemctl enable --now docker       # al encender la instancia, Docker levanta los contenedores solo
usermod -aG docker "$USUARIO"

echo "== Docker Compose $COMPOSE_VERSION"
if ! { [[ -x $PLUGIN ]] && echo "$COMPOSE_SHA256  $PLUGIN" | sha256sum -c --quiet 2>/dev/null; }; then
    mkdir -p "$(dirname "$PLUGIN")"
    curl -fsSL -o "$PLUGIN.tmp" \
        "https://github.com/docker/compose/releases/download/$COMPOSE_VERSION/docker-compose-linux-x86_64"
    echo "$COMPOSE_SHA256  $PLUGIN.tmp" | sha256sum -c --quiet \
        || { rm -f "$PLUGIN.tmp"; echo "ERROR: la descarga de Compose no coincide con su SHA-256" >&2; exit 2; }
    chmod 755 "$PLUGIN.tmp" && mv "$PLUGIN.tmp" "$PLUGIN"
fi

echo "== Swap de 2 GB"
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
    if [[ ! -f /swapfile ]]; then
        fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile
    fi
    swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap defaults 0 0' >> /etc/fstab

echo "== Carpetas de /opt/inventaio"
install -d -o "$USUARIO" -g "$USUARIO" -m 755 /opt/inventaio /opt/inventaio/versiones /opt/inventaio/volcados
install -d -o "$USUARIO" -g "$USUARIO" -m 700 /opt/inventaio/estado

echo "== Versiones"
docker version --format 'Docker {{.Server.Version}} (API {{.Server.APIVersion}})'
docker compose version
git --version
free -h | sed -n '1,3p'
docker compose ls >/dev/null && echo "Compose habla con Docker: listo"
echo "Sal con 'exit' y entra otra vez con 'sudo su - $USUARIO' para quedar en el grupo docker"

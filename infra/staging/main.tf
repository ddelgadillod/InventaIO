# InventAI/o — Staging en k3s con servicios serverless (fase 4 de docs/INFRA-k3s-serverless-requerimientos.md).
# Se aplica desde AWS CloudShell con despliegue/aws/tofu.sh (infra/README.md); el CI solo corre fmt y validate.

terraform {
  required_version = ">= 1.13.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # El estado, cifrado y con bloqueo nativo de S3 (P10). El nombre del bucket lleva el número de la cuenta, así que no
  # va aquí: lo pasa despliegue/aws/tofu.sh con -backend-config
  backend "s3" {
    key          = "staging/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "us-east-2"
  default_tags {
    tags = {
      Proyecto = "inventaio"
      Ambiente = "staging"
    }
  }
}

module "ambiente" {
  source = "../modulos/ambiente"

  ambiente = "staging"
  # Mientras convive con la máquina de compose, la nueva no lleva Ambiente=staging: el workflow «Desplegar» seguiría
  # encontrando dos. En el corte (fase 5) pasa a "staging"
  etiqueta_ambiente = var.etiqueta_ambiente
  tipo_instancia    = "t3.medium"
  dominio_origen    = var.dominio_origen
  correo_avisos     = var.correo_avisos
  bucket_volcados   = var.bucket_volcados
  rol_github        = "inventaio-gha-staging"

  # P16: de lunes a viernes a las 7:00 y todos los días a las 23:00, hora de Bogotá
  horario = {
    encender = "cron(0 7 ? * MON-FRI *)"
    apagar   = "cron(0 23 * * ? *)"
  }
  # Staging se puede reconstruir: sin protección contra el borrado
  proteger_borrado = false
}

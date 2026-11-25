data "aws_caller_identity" "cuenta" {}

data "aws_region" "actual" {}

# La AMI de Amazon Linux 2023 más reciente al crear la máquina. Después no se sigue (ignore_changes en la instancia):
# una AMI nueva no debe reemplazar la máquina
data "aws_ssm_parameter" "ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# La VPC por defecto, como la máquina de compose (fase 0: existe)
data "aws_vpc" "defecto" {
  default = true
}

data "aws_subnets" "defecto" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.defecto.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# Las IP con que CloudFront llega a los orígenes: lo único que entra por el 443
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

data "aws_cloudfront_cache_policy" "optimizada" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "sin_cache" {
  name = "Managed-CachingDisabled"
}

# Todo lo del visitante menos el Host: Caddy espera el nombre del origen, y CloudFront lo pone. No incluye
# CloudFront-Viewer-Address; la IP del visitante va al final de X-Forwarded-For (H25)
data "aws_cloudfront_origin_request_policy" "todo_menos_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

locals {
  nombre = "inventaio-${var.ambiente}"
  cuenta = data.aws_caller_identity.cuenta.account_id
  region = data.aws_region.actual.region
  subred = sort(data.aws_subnets.defecto.ids)[0]

  # Las cabeceras de seguridad de la web salen del mismo archivo que usa Nginx (INV-66 e INV-68): una sola fuente
  cabeceras_nginx = file("${path.module}/../../../frontend/nginx/cabeceras-seguridad.conf")
  csp             = regex("Content-Security-Policy \"([^\"]+)\"", local.cabeceras_nginx)[0]
  hsts_segundos   = tonumber(regex("Strict-Transport-Security \"max-age=([0-9]+)\"", local.cabeceras_nginx)[0])
}

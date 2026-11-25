# Los parámetros que conoce la infraestructura (/inventaio/<ambiente>/…). Los otros secretos (postgres-password y
# jwt-secret-key) los genera scripts/desplegar.sh en la máquina la primera vez, así que no pasan por el estado de
# OpenTofu; humo-email y humo-clave los pone la persona responsable (infra/README.md); tag-actual y tag-anterior los
# escribe cada despliegue

resource "aws_ssm_parameter" "origen_secreto" {
  name        = "/inventaio/${var.ambiente}/origen-secreto"
  description = "Cabecera secreta de CloudFront hacia el origen (X-Origen-Secreto)"
  type        = "SecureString"
  value       = random_password.origen.result
}

resource "aws_ssm_parameter" "dominio_origen" {
  name        = "/inventaio/${var.ambiente}/dominio-origen"
  description = "Nombre del origen: Caddy saca su certificado para él"
  type        = "String"
  value       = var.dominio_origen
}

resource "aws_ssm_parameter" "url_publica" {
  name        = "/inventaio/${var.ambiente}/url-publica"
  description = "URL pública (CloudFront): ahí corre el humo de cada despliegue"
  type        = "String"
  value       = "https://${aws_cloudfront_distribution.web.domain_name}"
}

# Para restaurar_staging.sh en la máquina (el bucket del traslado de la base)
resource "aws_ssm_parameter" "bucket_volcados" {
  name        = "/inventaio/${var.ambiente}/bucket-volcados"
  description = "Bucket del traslado de la base (volcados/)"
  type        = "String"
  value       = var.bucket_volcados
}

# Para el workflow «Publicar web» (.github/workflows/publicar-web.yml): dónde sube la web y qué distribución invalida
resource "aws_ssm_parameter" "bucket_web" {
  name        = "/inventaio/${var.ambiente}/bucket-web"
  description = "Bucket de la web compilada"
  type        = "String"
  value       = aws_s3_bucket.web.bucket
}

resource "aws_ssm_parameter" "distribucion_web" {
  name        = "/inventaio/${var.ambiente}/distribucion-web"
  description = "Distribución de CloudFront de la web"
  type        = "String"
  value       = aws_cloudfront_distribution.web.id
}

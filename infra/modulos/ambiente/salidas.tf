output "url_publica" {
  description = "La aplicación por CloudFront"
  value       = "https://${aws_cloudfront_distribution.web.domain_name}"
}

output "ip_elastica" {
  description = "La IP que va en DuckDNS para el nombre del origen"
  value       = aws_eip.maquina.public_ip
}

output "dominio_origen" {
  value = var.dominio_origen
}

output "bucket_web" {
  description = "Donde el workflow «Desplegar» publica la web compilada"
  value       = aws_s3_bucket.web.bucket
}

output "distribucion" {
  description = "La distribución de CloudFront que el workflow invalida después de publicar la web"
  value       = aws_cloudfront_distribution.web.id
}

output "instancia" {
  value = aws_instance.maquina.id
}

output "tema_avisos" {
  value = aws_sns_topic.avisos.arn
}

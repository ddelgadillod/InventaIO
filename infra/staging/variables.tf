variable "etiqueta_ambiente" {
  description = "Etiqueta Ambiente de la máquina: staging-k3s hasta el corte (fase 5), staging después"
  type        = string
  default     = "staging-k3s"
}

variable "dominio_origen" {
  description = "Subdominio de DuckDNS para el origen, apuntando a la IP elástica de la salida ip_elastica"
  type        = string
  default     = "inventaio-origen-stg.duckdns.org"
}

# Estas dos no van en el repositorio. Se ponen en infra/staging/privado.auto.tfvars (ignorado por git) en CloudShell,
# o OpenTofu las pregunta
variable "correo_avisos" {
  description = "Correo de las alarmas"
  type        = string
  sensitive   = true
}

variable "bucket_volcados" {
  description = "El bucket del traslado de la base (guía de staging, §0)"
  type        = string
}

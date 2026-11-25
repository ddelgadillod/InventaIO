variable "ambiente" {
  description = "staging o produccion: va en los nombres, en los parámetros (/inventaio/<ambiente>/) y en las etiquetas"
  type        = string

  validation {
    condition     = contains(["staging", "produccion"], var.ambiente)
    error_message = "El ambiente es staging o produccion."
  }
}

variable "etiqueta_ambiente" {
  description = <<-EOT
    Valor de la etiqueta Ambiente de la máquina. Session Manager y el workflow «Desplegar» eligen la máquina por esta
    etiqueta, así que la máquina nueva de staging lleva otra (staging-k3s) mientras convive con la de compose, y pasa a
    «staging» en el corte (fase 5)
  EOT
  type        = string
}

variable "tipo_instancia" {
  description = "t3.medium; t3.large si la medición deja menos del 25 % de memoria libre (P3)"
  type        = string
  default     = "t3.medium"
}

variable "disco_gb" {
  description = "Disco raíz gp3 cifrado"
  type        = number
  default     = 30
}

variable "dominio_origen" {
  description = "El nombre del origen (DuckDNS) que apunta a la IP elástica: Caddy saca su certificado para él y CloudFront lo usa como origen de /api/*"
  type        = string
}

variable "correo_avisos" {
  description = "Correo de las alarmas (SNS). Llega una confirmación que hay que aceptar. No va en el repositorio"
  type        = string
  sensitive   = true
}

variable "bucket_volcados" {
  description = "El bucket del traslado de la base (guía de staging, §0). La máquina lee y escribe en volcados/. No va en el repositorio"
  type        = string
}

variable "rol_github" {
  description = "El rol de GitHub del ambiente (fase 1). Recibe permiso para publicar la web en su bucket e invalidar la distribución"
  type        = string
}

variable "modelo_bedrock" {
  description = "Modelo de Bedrock que puede invocar la máquina (D-R3 de INV-67)"
  type        = string
  default     = "qwen.qwen3-32b-v1:0"
}

variable "repositorio" {
  description = "El repositorio público que clona el primer arranque"
  type        = string
  default     = "https://github.com/ddelgadillod/InventaIO.git"
}

variable "rama" {
  description = "La rama que clona el primer arranque: de ahí sale despliegue/preparar_k3s.sh"
  type        = string
  default     = "develop"
}

variable "horario" {
  description = "Encendido y apagado (EventBridge Scheduler, hora de Bogotá). null: siempre encendida, como producción"
  type = object({
    encender = string
    apagar   = string
  })
  default = null
}

variable "proteger_borrado" {
  description = "Protección contra el borrado de la máquina desde la API"
  type        = bool
  default     = true
}

variable "copias_dias" {
  description = "Días que se guarda la instantánea diaria del disco (P15)"
  type        = number
  default     = 7
}

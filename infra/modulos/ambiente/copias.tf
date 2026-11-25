# ── Instantánea diaria del disco (P15) ──────────────
# Data Lifecycle Manager toma las máquinas con la etiqueta Copias=diarias. A las 03:30 UTC (22:30 en Bogotá), antes
# del apagado de staging. Una instantánea de una máquina apagada también sirve

resource "aws_iam_role" "copias" {
  name        = "${local.nombre}-copias"
  description = "InventAI/o ${var.ambiente}: Data Lifecycle Manager toma y borra las instantáneas del disco"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "copias" {
  role       = aws_iam_role.copias.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "disco" {
  description        = "InventAIo ${var.ambiente} instantanea diaria del disco por ${var.copias_dias} dias"
  execution_role_arn = aws_iam_role.copias.arn
  state              = "ENABLED"

  policy_details {
    policy_type    = "EBS_SNAPSHOT_MANAGEMENT"
    resource_types = ["INSTANCE"]
    target_tags    = { Copias = "diarias", Proyecto = "inventaio" }

    schedule {
      name      = "diaria"
      copy_tags = true

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["03:30"]
      }

      retain_rule {
        count = var.copias_dias
      }
    }
  }
}

# ── Encendido y apagado (P16) ───────────────────────
# EventBridge Scheduler, en hora de Bogotá. Al encender, k3s levanta todo con el último tag desplegado; ponerse al día
# con develop lo hace la máquina misma al arrancar (fase 4, segunda parte)

resource "aws_iam_role" "horario" {
  count = var.horario == null ? 0 : 1

  name        = "${local.nombre}-horario"
  description = "InventAI/o ${var.ambiente}: EventBridge Scheduler enciende y apaga la máquina"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.cuenta } }
    }]
  })
}

resource "aws_iam_role_policy" "horario" {
  count = var.horario == null ? 0 : 1

  name = "encender-y-apagar"
  role = aws_iam_role.horario[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:StartInstances", "ec2:StopInstances"]
      Resource = aws_instance.maquina.arn
    }]
  })
}

resource "aws_scheduler_schedule" "maquina" {
  for_each = var.horario == null ? {} : {
    encender = { expresion = var.horario.encender, accion = "startInstances" }
    apagar   = { expresion = var.horario.apagar, accion = "stopInstances" }
  }

  name                         = "${local.nombre}-${each.key}"
  description                  = "InventAI/o ${var.ambiente}: ${each.key} la máquina"
  schedule_expression          = each.value.expresion
  schedule_expression_timezone = "America/Bogota"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:${each.value.accion}"
    role_arn = aws_iam_role.horario[0].arn
    input    = jsonencode({ InstanceIds = [aws_instance.maquina.id] })
  }
}

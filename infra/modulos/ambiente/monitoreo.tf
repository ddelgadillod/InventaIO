# ── Avisos por correo (P14) ─────────────────────────
# Las alarmas de la máquina; la memoria y el disco los publica el agente de CloudWatch (despliegue/preparar_k3s.sh).
# Sin datos (la máquina de staging apagada de noche) no cuentan como falla. El chequeo de salud de Route 53 y las
# alarmas de RDS y de CloudFront llegan con producción (fase 6)

resource "aws_sns_topic" "avisos" {
  name = "${local.nombre}-avisos"
}

resource "aws_sns_topic_subscription" "correo" {
  topic_arn = aws_sns_topic.avisos.arn
  protocol  = "email"
  endpoint  = var.correo_avisos
}

locals {
  alarmas = {
    # El equipo de AWS falla: la recupera en otro equipo, con el mismo disco y la misma IP
    chequeo-sistema = {
      descripcion = "Falló el chequeo del sistema de la EC2: AWS la recupera en otro equipo"
      espacio     = "AWS/EC2", metrica = "StatusCheckFailed_System", estadistica = "Maximum"
      comparacion = "GreaterThanOrEqualToThreshold", umbral = 1, periodo = 60, periodos = 2
      accion      = "arn:aws:automate:${local.region}:ec2:recover"
    }
    # El sistema de la máquina no responde: la reinicia, y k3s levanta todo solo
    chequeo-instancia = {
      descripcion = "Falló el chequeo de la instancia: se reinicia"
      espacio     = "AWS/EC2", metrica = "StatusCheckFailed_Instance", estadistica = "Maximum"
      comparacion = "GreaterThanOrEqualToThreshold", umbral = 1, periodo = 60, periodos = 3
      accion      = "arn:aws:automate:${local.region}:ec2:reboot"
    }
    cpu = {
      descripcion = "CPU por encima del 80 % durante 15 minutos"
      espacio     = "AWS/EC2", metrica = "CPUUtilization", estadistica = "Average"
      comparacion = "GreaterThanThreshold", umbral = 80, periodo = 300, periodos = 3
      accion      = null
    }
    # La t3 va en modo «unlimited»: sin créditos no se frena, y solo cuesta si en 24 horas no recupera lo que gastó de
    # más. Por eso avisa cuando AWS cobra créditos, no cuando quedan pocos: una máquina recién creada o recién
    # encendida arranca con pocos y eso no es un problema (fase 4)
    creditos-cobrados = {
      descripcion = "AWS cobró créditos de CPU por encima de la línea base (modo unlimited)"
      espacio     = "AWS/EC2", metrica = "CPUSurplusCreditsCharged", estadistica = "Sum"
      comparacion = "GreaterThanThreshold", umbral = 0, periodo = 3600, periodos = 1
      accion      = null
    }
    memoria = {
      descripcion = "Memoria por encima del 85 % durante 10 minutos"
      espacio     = "CWAgent", metrica = "mem_used_percent", estadistica = "Average"
      comparacion = "GreaterThanThreshold", umbral = 85, periodo = 300, periodos = 2
      accion      = null
    }
    disco = {
      descripcion = "Disco por encima del 80 %"
      espacio     = "CWAgent", metrica = "disk_used_percent", estadistica = "Maximum"
      comparacion = "GreaterThanThreshold", umbral = 80, periodo = 300, periodos = 1
      accion      = null
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "maquina" {
  for_each = local.alarmas

  alarm_name          = "${local.nombre}-${each.key}"
  alarm_description   = "InventAI/o ${var.ambiente}: ${each.value.descripcion}"
  namespace           = each.value.espacio
  metric_name         = each.value.metrica
  statistic           = each.value.estadistica
  comparison_operator = each.value.comparacion
  threshold           = each.value.umbral
  period              = each.value.periodo
  evaluation_periods  = each.value.periodos
  treat_missing_data  = "notBreaching"
  dimensions          = { InstanceId = aws_instance.maquina.id }
  alarm_actions       = compact([aws_sns_topic.avisos.arn, each.value.accion])
  ok_actions          = [aws_sns_topic.avisos.arn]
}

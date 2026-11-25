# ── Rol de la máquina ───────────────────────────────
# inventaio-<ambiente>-ec2: Session Manager, el agente de CloudWatch, Bedrock, los parámetros de su ambiente y el
# traslado de la base. En staging ya existía (guía de staging, §1): infra/staging lo adopta con bloques import.
# Lo usa también el agente desde su pod (el único que llega a los metadatos de la máquina, k8s/base/red.yaml)

resource "aws_iam_role" "maquina" {
  name        = "${local.nombre}-ec2"
  description = "InventAI/o ${var.ambiente}: Session Manager, CloudWatch, Bedrock, Parameter Store y el traslado de la base"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_instance_profile" "maquina" {
  name = aws_iam_role.maquina.name
  role = aws_iam_role.maquina.name
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.maquina.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch" {
  role       = aws_iam_role.maquina.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_role_policy" "maquina" {
  name = coalesce(var.politica_maquina, local.nombre)
  role = aws_iam_role.maquina.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Bedrock"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "arn:aws:bedrock:${local.region}::foundation-model/${var.modelo_bedrock}"
      },
      {
        # scripts/desplegar.sh: los secretos (los genera la primera vez), el origen, la URL pública y los tags
        Sid      = "ParametrosDelAmbiente"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath", "ssm:PutParameter"]
        Resource = "arn:aws:ssm:${local.region}:${local.cuenta}:parameter/inventaio/${var.ambiente}/*"
      },
      {
        Sid      = "Volcados"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "arn:aws:s3:::${var.bucket_volcados}/volcados/*"
      },
      {
        Sid       = "ListarVolcados"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = "arn:aws:s3:::${var.bucket_volcados}"
        Condition = { StringLike = { "s3:prefix" = ["volcados/*"] } }
      },
    ]
  })
}

# ── Red ─────────────────────────────────────────────
# Dos grupos: la lista de CloudFront ocupa casi todas las reglas de uno (fase 0). El 22 y el 6443 (API de Kubernetes)
# quedan cerrados: se entra por Session Manager

resource "aws_security_group" "origen_443" {
  name        = "${local.nombre}-origen-443"
  description = "InventAI/o ${var.ambiente}: el 443 solo desde CloudFront"
  vpc_id      = data.aws_vpc.defecto.id
  tags        = { Name = "${local.nombre}-origen-443" }
}

resource "aws_vpc_security_group_ingress_rule" "cloudfront" {
  security_group_id = aws_security_group.origen_443.id
  description       = "CloudFront hacia Caddy"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
}

resource "aws_vpc_security_group_egress_rule" "salida" {
  security_group_id = aws_security_group.origen_443.id
  description       = "Salida: imagenes, Lets Encrypt, Bedrock, Parameter Store, S3 y CloudWatch"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_security_group" "origen_80" {
  name        = "${local.nombre}-origen-80"
  description = "InventAI/o ${var.ambiente}: el 80 para el desafio de Lets Encrypt y la redireccion"
  vpc_id      = data.aws_vpc.defecto.id
  tags        = { Name = "${local.nombre}-origen-80" }
}

resource "aws_vpc_security_group_ingress_rule" "acme" {
  security_group_id = aws_security_group.origen_80.id
  description       = "Desafio HTTP de Lets Encrypt"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

# ── Máquina ─────────────────────────────────────────

resource "aws_instance" "maquina" {
  ami                     = data.aws_ssm_parameter.ami.insecure_value
  instance_type           = var.tipo_instancia
  subnet_id               = local.subred
  vpc_security_group_ids  = [aws_security_group.origen_443.id, aws_security_group.origen_80.id]
  iam_instance_profile    = aws_iam_instance_profile.maquina.name
  disable_api_termination = var.proteger_borrado

  # IMDSv2 con dos saltos: los pods quedan un salto más lejos de los metadatos que la máquina (H21)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.disco_gb
    encrypted   = true
    tags        = { Name = "${local.nombre}-k3s" }
  }

  # El primer arranque clona el repositorio y corre despliegue/preparar_k3s.sh
  user_data = templatefile("${path.module}/arranque.sh.tftpl", {
    ambiente    = var.ambiente
    repositorio = var.repositorio
    rama        = var.rama
  })

  tags = {
    Name     = "${local.nombre}-k3s"
    Ambiente = var.etiqueta_ambiente
    # La toma la política de instantáneas diarias (copias.tf)
    Copias = "diarias"
  }

  lifecycle {
    # Una AMI o un primer arranque nuevos no reemplazan la máquina: se reconstruye a propósito (tofu apply -replace)
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "maquina" {
  domain   = "vpc"
  instance = aws_instance.maquina.id
  tags     = { Name = "${local.nombre}-k3s" }
}

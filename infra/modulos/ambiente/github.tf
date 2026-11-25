# El rol de GitHub del ambiente (lo creó la fase 1 con despliegue/aws/fase1_despliegue_automatico.sh) recibe una
# política más, sin que OpenTofu tome el rol: publicar la web compilada en su bucket e invalidar su distribución,
# leyendo de Parameter Store dónde están

resource "aws_iam_role_policy" "github_web" {
  name = "web"
  role = var.rol_github
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PublicarLaWeb"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.web.arn}/*"
      },
      {
        Sid      = "ListarLaWeb"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.web.arn
      },
      {
        Sid      = "Invalidar"
        Effect   = "Allow"
        Action   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
        Resource = aws_cloudfront_distribution.web.arn
      },
      {
        # Ninguno es secreto: el workflow sabe así dónde publicar sin variables a mano en GitHub
        Sid    = "DondePublicar"
        Effect = "Allow"
        Action = "ssm:GetParameter"
        Resource = [
          aws_ssm_parameter.bucket_web.arn,
          aws_ssm_parameter.distribucion_web.arn,
          aws_ssm_parameter.url_publica.arn,
        ]
      },
    ]
  })
}

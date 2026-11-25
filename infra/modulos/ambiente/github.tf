# El rol de GitHub del ambiente (lo creó la fase 1 con despliegue/aws/fase1_despliegue_automatico.sh) recibe una
# política más, sin que OpenTofu tome el rol: publicar la web compilada en su bucket e invalidar su distribución

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
    ]
  })
}

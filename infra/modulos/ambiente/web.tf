# ── La web en S3 y CloudFront (P5) ──────────────────
#   /*      → el bucket privado con la aplicación compilada (la sube el workflow «Desplegar» desde la imagen web)
#   /api/*  → la máquina: Caddy en el 443, que exige la cabecera secreta de origen
# Con el dominio de GitHub Student (P6) se agregan el certificado de ACM y el nombre alternativo; mientras, la URL es la
# de CloudFront

resource "aws_s3_bucket" "web" {
  bucket_prefix = "${local.nombre}-web-"
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Con versiones, para volver a una web anterior
resource "aws_s3_bucket_versioning" "web" {
  bucket = aws_s3_bucket.web.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    id     = "versiones-viejas"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${local.nombre}-web"
  description                       = "InventAI/o ${var.ambiente}: solo CloudFront lee el bucket de la web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "SoloCloudFront"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.web.arn}/*"
        Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.web.arn } }
      },
      {
        Sid       = "SoloTLS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.web.arn, "${aws_s3_bucket.web.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.web]
}

resource "aws_cloudfront_function" "spa" {
  name    = "${local.nombre}-spa"
  runtime = "cloudfront-js-2.0"
  comment = "Rutas de la SPA a index.html"
  publish = true
  code    = file("${path.module}/spa.js")
}

# Las mismas cabeceras que pone Nginx (frontend/nginx/cabeceras-seguridad.conf): la CSP de INV-68 y HSTS sin subdominios
resource "aws_cloudfront_response_headers_policy" "seguridad" {
  name    = "${local.nombre}-seguridad"
  comment = "InventAI/o ${var.ambiente}: CSP, HSTS y cabeceras de seguridad de la web"

  security_headers_config {
    content_security_policy {
      content_security_policy = local.csp
      override                = true
    }
    strict_transport_security {
      access_control_max_age_sec = local.hsts_segundos
      include_subdomains         = false
      preload                    = false
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
  }
}

# El secreto de origen: CloudFront lo manda en cada petición a la máquina y Caddy lo exige (k8s/base/Caddyfile).
# Vive en el estado de OpenTofu (bucket cifrado y privado) y en Parameter Store, de donde lo toma scripts/desplegar.sh
resource "random_password" "origen" {
  length  = 48
  special = false
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  comment             = "InventAI/o ${var.ambiente}"
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_All"
  default_root_object = "index.html"

  origin {
    origin_id                = "web"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    origin_id   = "maquina"
    domain_name = var.dominio_origen

    custom_origin_config {
      origin_protocol_policy = "https-only"
      http_port              = 80
      https_port             = 443
      origin_ssl_protocols   = ["TLSv1.2"]
      # El máximo sin pedir cuota. El chat manda un ping cada 15 s y las recomendaciones en frío tardan hasta 42 s (H24)
      origin_read_timeout      = 60
      origin_keepalive_timeout = 5
    }

    custom_header {
      name  = "X-Origen-Secreto"
      value = random_password.origen.result
    }
  }

  default_cache_behavior {
    target_origin_id           = "web"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimizada.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.seguridad.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }

  # La API, sin caché. Sin compresión: el chat es un flujo de eventos (text/event-stream) que debe salir apenas llega
  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "maquina"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = false
    cache_policy_id          = data.aws_cloudfront_cache_policy.sin_cache.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.todo_menos_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

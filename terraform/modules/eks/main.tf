terraform {
  required_version = ">= 1.7"
  required_providers {
    aws  = { source = "hashicorp/aws", version = "~> 5.40" }
    helm = { source = "hashicorp/helm", version = "~> 2.13" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.30" }
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.20"

  cluster_name    = "colab-${var.env}"
  cluster_version = var.cluster_version

  cluster_endpoint_public_access = true

  enable_cluster_creator_admin_permissions = true

  vpc_id     = var.vpc_id
  subnet_ids = var.subnet_ids

  cluster_addons = {
    vpc-cni = {
      most_recent              = true
      service_account_role_arn = aws_iam_role.vpc_cni.arn
    }
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = aws_iam_role.ebs_csi.arn
    }
  }

  eks_managed_node_groups = {
    for name, cfg in var.node_groups : name => {
      name           = name
      instance_types = cfg.instance_types
      capacity_type  = try(cfg.capacity_type, "ON_DEMAND")
      desired_size   = cfg.desired_size
      min_size       = cfg.min_size
      max_size       = cfg.max_size
      taints         = try(cfg.taints, [])
      labels = {
        env       = var.env
        nodegroup = name
      }
    }
  }

  tags = { Project = "colab", Env = var.env }
}

# ----- IRSA roles for core addons -----
data "aws_iam_policy_document" "irsa_assume" {
  for_each = toset(["vpc_cni", "ebs_csi", "alb_controller", "external_dns", "external_secrets"])

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(module.eks.cluster_oidc_issuer_url, "https://", "")}:sub"
      values   = [local.irsa_subjects[each.key]]
    }
  }
}

locals {
  irsa_subjects = {
    vpc_cni          = "system:serviceaccount:kube-system:aws-node"
    ebs_csi          = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
    alb_controller   = "system:serviceaccount:kube-system:aws-load-balancer-controller"
    external_dns     = "system:serviceaccount:kube-system:external-dns"
    external_secrets = "system:serviceaccount:external-secrets:external-secrets"
  }
}

resource "aws_iam_role" "vpc_cni" {
  name               = "colab-${var.env}-vpc-cni"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume["vpc_cni"].json
}

resource "aws_iam_role_policy_attachment" "vpc_cni" {
  role       = aws_iam_role.vpc_cni.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role" "ebs_csi" {
  name               = "colab-${var.env}-ebs-csi"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume["ebs_csi"].json
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_iam_role" "alb_controller" {
  name               = "colab-${var.env}-alb-controller"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume["alb_controller"].json
}

resource "aws_iam_role_policy" "alb_controller" {
  role   = aws_iam_role.alb_controller.id
  policy = file("${path.module}/policies/alb-controller.json")
}

resource "aws_iam_role" "external_dns" {
  name               = "colab-${var.env}-external-dns"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume["external_dns"].json
}

resource "aws_iam_role_policy" "external_dns" {
  role = aws_iam_role.external_dns.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "route53:ChangeResourceRecordSets",
          "route53:ListResourceRecordSets",
          "route53:GetHostedZone",
          "route53:ListHostedZones",
          "route53:ListHostedZonesByName",
          "route53:ListTagsForResource"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "external_secrets" {
  name               = "colab-${var.env}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume["external_secrets"].json
}

resource "aws_iam_role_policy" "external_secrets" {
  role = aws_iam_role.external_secrets.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = "arn:aws:secretsmanager:*:*:secret:colab/${var.env}/*"
    }]
  })
}

# ----- Helm addons -----
provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    }
  }
}

resource "helm_release" "aws_lb_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  namespace  = "kube-system"
  version    = "1.8.1"

  values = [yamlencode({
    clusterName = module.eks.cluster_name
    region      = data.aws_region.current.name
    vpcId       = var.vpc_id
    serviceAccount = {
      create = true
      name   = "aws-load-balancer-controller"
      annotations = {
        "eks.amazonaws.com/role-arn" = aws_iam_role.alb_controller.arn
      }
    }
  })]

  depends_on = [module.eks]
}

resource "helm_release" "external_dns" {
  name       = "external-dns"
  repository = "https://kubernetes-sigs.github.io/external-dns/"
  chart      = "external-dns"
  namespace  = "kube-system"
  version    = "1.14.5"

  values = [yamlencode({
    provider = "aws"
    aws = { region = data.aws_region.current.name }
    serviceAccount = {
      create = true
      name   = "external-dns"
      annotations = {
        "eks.amazonaws.com/role-arn" = aws_iam_role.external_dns.arn
      }
    }
    txtOwnerId = "colab-${var.env}"
    policy     = "sync"
  })]

  depends_on = [module.eks]
}

resource "helm_release" "cert_manager" {
  name             = "cert-manager"
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  namespace        = "cert-manager"
  version          = "1.15.0"
  create_namespace = true

  set {
    name  = "installCRDs"
    value = "true"
  }

  depends_on = [module.eks]
}

resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  namespace        = "external-secrets"
  version          = "0.9.20"
  create_namespace = true

  values = [yamlencode({
    serviceAccount = {
      create = true
      name   = "external-secrets"
      annotations = {
        "eks.amazonaws.com/role-arn" = aws_iam_role.external_secrets.arn
      }
    }
    installCRDs = true
  })]

  depends_on = [module.eks]
}

resource "helm_release" "metrics_server" {
  name       = "metrics-server"
  repository = "https://kubernetes-sigs.github.io/metrics-server/"
  chart      = "metrics-server"
  namespace  = "kube-system"
  version    = "3.12.1"

  depends_on = [module.eks]
}

# ClusterSecretStore for ESO (created via kubectl manifest applied post-Helm)
resource "kubernetes_manifest" "cluster_secret_store" {
  manifest = {
    apiVersion = "external-secrets.io/v1beta1"
    kind       = "ClusterSecretStore"
    metadata   = { name = "colab-cluster-store" }
    spec = {
      provider = {
        aws = {
          service = "SecretsManager"
          region  = data.aws_region.current.name
          auth = {
            jwt = {
              serviceAccountRef = {
                name      = "external-secrets"
                namespace = "external-secrets"
              }
            }
          }
        }
      }
    }
  }

  depends_on = [helm_release.external_secrets]
}

data "aws_region" "current" {}

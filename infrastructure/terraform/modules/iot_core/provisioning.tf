# ============================================================
# Fleet Provisioning IAM Role
# ============================================================
resource "aws_iam_role" "fleet_provisioning" {
  name = "${local.name}-fleet-provisioning-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "iot.amazonaws.com" }
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "fleet_provisioning" {
  name = "${local.name}-fleet-provisioning-policy"
  role = aws_iam_role.fleet_provisioning.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "iot:CreateThing",
        "iot:DescribeThing",
        "iot:RegisterThing",
        "iot:AttachPolicy",
        "iot:AttachThingPrincipal",
        "iot:UpdateCertificate",
        "iot:CreateCertificateFromCsr",
        "iot:AddThingToThingGroup",
      ]
      Resource = "*"
    }]
  })
}

# ============================================================
# Claim Certificate Policy (bootstrap — provisioning only)
# ============================================================
resource "aws_iot_policy" "claim" {
  name = "${local.name}-claim-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["iot:Connect"]
        Resource = "arn:aws:iot:${var.region}:${var.account_id}:client/provisioning-*"
      },
      {
        Effect = "Allow"
        Action = ["iot:Publish"]
        Resource = [
          "arn:aws:iot:${var.region}:${var.account_id}:topic/$aws/certificates/create/json",
          "arn:aws:iot:${var.region}:${var.account_id}:topic/$aws/provisioning-templates/${local.name}-fleet-template/provision/json",
        ]
      },
      {
        Effect = "Allow"
        Action = ["iot:Subscribe"]
        Resource = [
          "arn:aws:iot:${var.region}:${var.account_id}:topicfilter/$aws/certificates/create/json/*",
          "arn:aws:iot:${var.region}:${var.account_id}:topicfilter/$aws/provisioning-templates/${local.name}-fleet-template/provision/json/*",
        ]
      },
      {
        Effect = "Allow"
        Action = ["iot:Receive"]
        Resource = [
          "arn:aws:iot:${var.region}:${var.account_id}:topic/$aws/certificates/create/json/*",
          "arn:aws:iot:${var.region}:${var.account_id}:topic/$aws/provisioning-templates/${local.name}-fleet-template/provision/json/*",
        ]
      },
    ]
  })
}

# ============================================================
# IoT Thing Group — all fleet robots land here
# ============================================================
resource "aws_iot_thing_group" "fleet" {
  name = "${local.name}-robots"
  tags = local.tags
}

# ============================================================
# Fleet Provisioning Template
# ============================================================
resource "aws_iot_provisioning_template" "fleet" {
  name                  = "${local.name}-fleet-template"
  description           = "Fleet provisioning for RobotOps cleaning robots"
  provisioning_role_arn = aws_iam_role.fleet_provisioning.arn
  enabled               = true

  # Template body is evaluated by AWS at provisioning time.
  # Terraform resolves the policy name before storing the JSON.
  template_body = jsonencode({
    Parameters = {
      SerialNumber = { Type = "String" }
      "AWS::IoT::Certificate::Id" = { Type = "String" }
    }
    Resources = {
      thing = {
        Type = "AWS::IoT::Thing"
        Properties = {
          ThingName   = { "Fn::Join" = ["-", ["robot", { Ref = "SerialNumber" }]] }
          ThingGroups = [aws_iot_thing_group.fleet.name]
        }
      }
      certificate = {
        Type = "AWS::IoT::Certificate"
        Properties = {
          CertificateId = { Ref = "AWS::IoT::Certificate::Id" }
          Status        = "Active"
        }
      }
      policy = {
        Type = "AWS::IoT::Policy"
        Properties = {
          PolicyName = aws_iot_policy.robot.name
        }
      }
    }
  })

  tags = local.tags
}

## Despliegue con env0 (Plantilla EC2 + ALB + Okta)

Este documento resume los pasos mínimos para desplegar la aplicación usando la plantilla `aws-public-app-ec2` y un repositorio privado en ECR.

### 1) Repositorio ECR
- Crea (si no existe) el repo con la plantilla env0 `aws-ecr-private-repository`.
- Variables recomendadas:
  - `repository_name`: `smart-scout-app`
  - `scan_on_push`: `true`
  - `lifecycle_policy`: mantener 10 imágenes más recientes

### 2) CI/CD GitHub Actions
- Workflow: `.github/workflows/ecr-build-push.yml`.
- Requisitos:
  - `secrets.AWS_ROLE_TO_ASSUME`: ARN del rol con permisos de push a ECR.
  - `vars.AWS_REGION`: región (p. ej. `us-east-1`).
  - `vars.ECR_REPOSITORY`: nombre del repo (p. ej. `smart-scout-app`).

### 3) Plantilla env0 `aws-public-app-ec2`
- Variables clave:
  - `vpc_name`: VPC existente.
  - `instance_type`: `t3.medium` (o el requerido).
  - `instance_num`: `1` (o ASG>1 si quieres autoescalado).
  - `os`: `Ubuntu xx.04`.
  - `custom_hostnames`: ["<tu-nombre>.bain.dev"] si aplica.
  - `okta_client_id`, `okta_client_secret`, `issuer_url`.
- Healthcheck: expón `/health` en la app para el target group.

### 4) EC2 user data
- Script: `scripts/ec2_user_data.sh`.
- Parámetros que puedes pasar como user data (opcional):
  - `ECR_REPOSITORY`, `IMAGE_TAG`, `APP_PORT`.
- El script realiza login a ECR, descarga la imagen y la ejecuta.

### 5) Flujo de despliegue
1. Merge a la rama con el workflow de CI para publicar la imagen (o `workflow_dispatch`).
2. Ejecuta la plantilla EC2 en env0, verifica los `outputs` y la URL `app_url`.
3. Comprobar acceso vía Okta y respuesta del endpoint `/health`.

### 6) Permisos IAM mínimos
- Rol de CI (GitHub Actions): `ecr:BatchGetImage`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:GetAuthorizationToken`.
- Rol de instancia EC2: `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, opcional `logs:*` para CloudWatch Logs.



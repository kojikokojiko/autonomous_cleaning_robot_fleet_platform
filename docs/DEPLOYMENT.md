# デプロイ手順書

## 初回デプロイ（環境構築）

### 前提条件

以下がインストール済みであること：

| ツール | 確認コマンド |
|---|---|
| AWS CLI | `aws --version` |
| Terraform v1.6+ | `terraform version` |
| Docker | `docker --version` |
| Python 3.11 | `python3 --version` |
| Node.js 20 | `node --version` |
| GitHub CLI | `gh --version` |

---

### Step 0: AWS CLI の設定（1回のみ）

AWS ConsoleでIAMユーザーのアクセスキーを発行してから実行する。

```bash
aws configure
# AWS Access Key ID:     （IAMユーザーのアクセスキーID）
# AWS Secret Access Key: （IAMユーザーのシークレットアクセスキー）
# Default region name:   ap-northeast-1
# Default output format: json
```

設定確認：

```bash
aws sts get-caller-identity
# {
#   "UserId": "AIDAXXXXXXXXXXXXXXXXX",
#   "Account": "123456789012",
#   "Arn": "arn:aws:iam::123456789012:user/your-name"
# }
```

> **IAMユーザーに必要な権限**: AdministratorAccess（または Terraform が必要とするリソースへのフルアクセス）

---

### Step 1: Terraform State Backend を作成（1回のみ）

```bash
# S3バケット作成
aws s3api create-bucket \
  --bucket robotops-terraform-state \
  --region ap-northeast-1 \
  --create-bucket-configuration LocationConstraint=ap-northeast-1

aws s3api put-bucket-versioning \
  --bucket robotops-terraform-state \
  --versioning-configuration Status=Enabled

# DynamoDBテーブル作成（Terraformのロック用）
aws dynamodb create-table \
  --table-name robotops-terraform-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-northeast-1
```

---

### Step 2: Lambda zip ファイルのビルド

`terraform apply` の前に必須。zip が存在しないと plan 時にエラーになる。

```bash
bash lambda/build.sh
# → lambda/telemetry-processor/function.zip
# → lambda/ws-connection-manager/function.zip
# → lambda/ws-event-pusher/function.zip
```

---

### Step 3: terraform apply

```bash
cd infrastructure/terraform/environments/dev

terraform init
terraform plan   # 変更内容を確認
terraform apply  # 約20〜30分
```

完了したら以下を記録しておく：

```bash
terraform output  # 以下の値が出力される
# api_endpoint               = "https://xxxxx.execute-api.ap-northeast-1.amazonaws.com"
# ws_endpoint                = "wss://xxxxx.execute-api.ap-northeast-1.amazonaws.com/dev"
# dashboard_url              = "https://xxxxx.cloudfront.net"
# github_actions_role_arn    = "arn:aws:iam::xxxx:role/..."
# dashboard_bucket           = "robotops-dev-dashboard-xxxx"
# cloudfront_distribution_id = "XXXXXXXXXXXXX"
```

---

### Step 4: DBスキーマ適用

RDSはプライベートサブネット内のため、AWS ConsoleのRDS Query Editorから実行する。

1. AWS Console → RDS → データベース → robotops-dev を選択
2. 「クエリエディタ」→ `infrastructure/db/init.sql` の内容を貼り付けて実行

---

### Step 5: GitHubリポジトリ作成

```bash
gh repo create autonomous_cleaning_robot_fleet_platform --public
git remote add origin https://github.com/<your-username>/autonomous_cleaning_robot_fleet_platform.git
```

---

### Step 6: terraform.tfvars のリポジトリ名を更新

```bash
# infrastructure/terraform/environments/dev/terraform.tfvars
github_repo = "<your-username>/autonomous_cleaning_robot_fleet_platform"
```

---

### Step 7: GitHub Secrets を設定

```bash
export GITHUB_REPO=<your-username>/autonomous_cleaning_robot_fleet_platform
./scripts/setup_github_secrets.sh
```

設定される値：

| 種別 | キー | 値の取得元 |
|---|---|---|
| Secret | `AWS_ROLE_ARN` | terraform output |
| Secret | `AWS_ACCOUNT_ID` | terraform output |
| Secret | `DASHBOARD_BUCKET` | terraform output |
| Secret | `CLOUDFRONT_DISTRIBUTION_ID` | terraform output |
| Variable | `VITE_API_URL` | terraform output (api_endpoint) |
| Variable | `VITE_WS_URL` | terraform output (ws_endpoint) |

---

### Step 8: git push → CI/CD が全自動デプロイ

```bash
git add .
git commit -m "initial deployment"
git push origin main
```

GitHub Actions が自動で以下を実行：

```
backend-ci.yml
  → テスト（5サービス）
  → Dockerビルド → ECRプッシュ（6サービス）
  → ECSローリングデプロイ

dashboard-ci.yml
  → npm run build
  → S3アップロード
  → CloudFrontキャッシュ削除

lambda-ci.yml
  → lambda/build.sh
  → Lambda関数を更新
```

---

### Step 9: 動作確認

```bash
terraform output dashboard_url
# → ブラウザで開く
```

---

## 2回目以降：アプリコードの変更

コードを変更して `git push` するだけ。CI/CDが自動対応。

| 変更箇所 | 自動実行されるワークフロー |
|---|---|
| `backend-services/**` | backend-ci.yml（テスト→ビルド→ECSデプロイ） |
| `dashboard/**` | dashboard-ci.yml（ビルド→S3→CloudFront） |
| `lambda/**` | lambda-ci.yml（ビルド→Lambda更新） |

---

## 2回目以降：インフラの変更

GitHub Actions の手動実行から行う。

```
GitHub → Actions タブ → Terraform CI/CD → Run workflow
  → action: plan   （変更内容を確認するだけ）
  → action: apply  （実際に適用）
```

**推奨フロー：**
1. ブランチでTerraformコードを変更
2. PRを出す → Plan結果がPRにコメントされる
3. 内容を確認してマージ
4. Actions タブから手動で `apply` を実行

---

## インフラを全削除する場合

```
GitHub → Actions タブ → Terraform CI/CD → Run workflow
  → action: destroy
```

または手動：

```bash
cd infrastructure/terraform/environments/dev
terraform destroy
```

> **注意**: terraform destroy ではS3バケット（ファームウェア・ダッシュボード）は削除されない場合がある。AWS Consoleから手動で削除すること。

---

## トラブルシューティング

### ECSサービスが起動しない
→ ECRにイメージがプッシュされているか確認。初回はCI/CDが完走してから数分後に起動する。

### terraform apply が失敗する（Lambda zip not found）
→ `bash lambda/build.sh` を先に実行すること。

### GitHub Actionsが `AWS_ROLE_ARN` エラーで失敗する
→ Step 7の `setup_github_secrets.sh` が完了しているか確認。

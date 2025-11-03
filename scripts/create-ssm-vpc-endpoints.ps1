# Create VPC endpoints for SSM Session Manager
# This allows EC2 instances in private subnets to connect to SSM without internet access

$VPC_ID = "vpc-0db5698e5cb443dbf"
$SUBNET_ID = "subnet-0995876dededa596d"
$SG_ID = "sg-05086b4bff4981532"
$REGION = "us-east-1"
$PROFILE = "KikeRev"

Write-Host "Creating VPC endpoints for SSM..." -ForegroundColor Cyan

# 1. SSM endpoint
Write-Host "`nCreating SSM endpoint..." -ForegroundColor Yellow
$ssmEndpoint = aws ec2 create-vpc-endpoint `
    --vpc-id $VPC_ID `
    --vpc-endpoint-type Interface `
    --service-name "com.amazonaws.$REGION.ssm" `
    --subnet-ids $SUBNET_ID `
    --security-group-ids $SG_ID `
    --region $REGION `
    --profile $PROFILE `
    --output json | ConvertFrom-Json

if ($ssmEndpoint.VpcEndpoint.VpcEndpointId) {
    Write-Host "✅ SSM endpoint created: $($ssmEndpoint.VpcEndpoint.VpcEndpointId)" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to create SSM endpoint" -ForegroundColor Red
    exit 1
}

# 2. SSM Messages endpoint
Write-Host "`nCreating SSM Messages endpoint..." -ForegroundColor Yellow
$ssmMessagesEndpoint = aws ec2 create-vpc-endpoint `
    --vpc-id $VPC_ID `
    --vpc-endpoint-type Interface `
    --service-name "com.amazonaws.$REGION.ssmmessages" `
    --subnet-ids $SUBNET_ID `
    --security-group-ids $SG_ID `
    --region $REGION `
    --profile $PROFILE `
    --output json | ConvertFrom-Json

if ($ssmMessagesEndpoint.VpcEndpoint.VpcEndpointId) {
    Write-Host "✅ SSM Messages endpoint created: $($ssmMessagesEndpoint.VpcEndpoint.VpcEndpointId)" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to create SSM Messages endpoint" -ForegroundColor Red
    exit 1
}

# 3. EC2 Messages endpoint
Write-Host "`nCreating EC2 Messages endpoint..." -ForegroundColor Yellow
$ec2MessagesEndpoint = aws ec2 create-vpc-endpoint `
    --vpc-id $VPC_ID `
    --vpc-endpoint-type Interface `
    --service-name "com.amazonaws.$REGION.ec2messages" `
    --subnet-ids $SUBNET_ID `
    --security-group-ids $SG_ID `
    --region $REGION `
    --profile $PROFILE `
    --output json | ConvertFrom-Json

if ($ec2MessagesEndpoint.VpcEndpoint.VpcEndpointId) {
    Write-Host "✅ EC2 Messages endpoint created: $($ec2MessagesEndpoint.VpcEndpoint.VpcEndpointId)" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to create EC2 Messages endpoint" -ForegroundColor Red
    exit 1
}

Write-Host "`n✨ All VPC endpoints created successfully!" -ForegroundColor Green
Write-Host "⏳ Wait 2-3 minutes for endpoints to become available, then try connecting:" -ForegroundColor Cyan
Write-Host "   aws ssm start-session --target i-0d0fbe9369d415be0 --region $REGION --profile $PROFILE" -ForegroundColor White



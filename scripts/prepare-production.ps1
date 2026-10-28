param(
    [Parameter(Mandatory = $true)]
    [string]$Domain,
    [string]$OutputDirectory = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$Domain = $Domain.ToLowerInvariant()
if ($Domain -notmatch '^(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,63}$' -or
    $Domain -match '(?i)\.(local|localhost|internal|test|invalid)$') {
    throw 'Provide a public domain only, without https://, a port, or a path.'
}
foreach ($label in $Domain.Split('.')) {
    if ($label -notmatch '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$') {
        throw 'Invalid DNS label in domain.'
    }
}
$resolvedDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$destination = Join-Path $resolvedDirectory '.env.production'
if (Test-Path -LiteralPath $destination) {
    throw 'An existing .env.production was found. It was not overwritten. Keep existing encryption keys.'
}

function New-PrivateSecret {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$databasePassword = New-PrivateSecret
$settings = [ordered]@{
    PAYSEAL_DOMAIN = $Domain.ToLowerInvariant()
    ENVIRONMENT = 'production'
    POSTGRES_PASSWORD = $databasePassword
    DATABASE_URL = "postgresql+psycopg://payseal:${databasePassword}@postgres:5432/payseal"
    JWT_SECRET = (New-PrivateSecret)
    JWT_ACCESS_TTL_MINUTES = '15'
    REFRESH_TOKEN_TTL_DAYS = '14'
    REFRESH_TOKEN_SECRET = (New-PrivateSecret)
    REFRESH_COOKIE_SECURE = 'true'
    ACCOUNT_ENCRYPTION_KEY = (New-PrivateSecret)
    ACCOUNT_LOOKUP_HMAC_KEY = (New-PrivateSecret)
    KEY_ENCRYPTION_SECRET = (New-PrivateSecret)
    PAYSEAL_ROOT_KEY_PATH = '/keys/root-private.pem.enc'
    PAYSEAL_ROOT_PUBLIC_KEY_PATH = '/keys/root-public.pem'
    SIGNING_KEY_DIRECTORY = '/keys/organizations'
    MINIO_ENDPOINT = 'minio:9000'
    MINIO_ACCESS_KEY = ('payseal-' + (New-PrivateSecret).Substring(0, 16))
    MINIO_SECRET_KEY = (New-PrivateSecret)
    MINIO_BUCKET = 'payseal-documents'
    MINIO_SECURE = 'false'
    PUBLIC_APP_URL = "https://$Domain"
    PUBLIC_VERIFY_BASE_URL = "https://$Domain/r"
    CORS_ORIGINS = "https://$Domain"
    TRUSTED_HOSTS = "localhost,backend,$Domain"
    NEXT_PUBLIC_API_BASE_URL = '/api/v1'
    TRANSFER_MODE = 'disabled'
    PAYMENTS_LIVE_ENABLED = 'false'
    MAX_LIVE_TRANSFER_AMOUNT = '1000000'
    TRANSFER_WEBHOOK_SECRET = ''
    MAX_PDF_BYTES = '10485760'
    MAX_BUSINESS_DOCUMENT_BYTES = '5242880'
    MFA_RECENT_WINDOW_SECONDS = '300'
}
$content = ($settings.GetEnumerator() | ForEach-Object { "{0}={1}" -f $_.Key, $_.Value }) -join "`n"
[IO.File]::WriteAllText($destination, $content + "`n", (New-Object Text.UTF8Encoding($false)))
if ($env:OS -eq 'Windows_NT') {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = Get-Acl -LiteralPath $destination
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $destination -AclObject $acl
} else {
    & chmod 600 -- $destination
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict secret-file permissions.' }
}
Write-Output "Created private configuration: $destination"
Write-Output 'Live payments remain disabled. No account, server, domain, or payment was created.'

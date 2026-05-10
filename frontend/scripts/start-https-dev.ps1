$ErrorActionPreference = "Stop"

$frontendDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$certDir = Join-Path $frontendDir "certs"
$pfxPath = Join-Path $certDir "dev.pfx"
$password = if ($env:VITE_HTTPS_CERT_PASSWORD) { $env:VITE_HTTPS_CERT_PASSWORD } else { "blind-ocr-dev" }

New-Item -ItemType Directory -Force -Path $certDir | Out-Null

if (-not (Test-Path $pfxPath)) {
    $ipAddresses = ipconfig |
        Select-String -Pattern "IPv4 Address.*?:\s*([0-9.]+)" |
        ForEach-Object { $_.Matches[0].Groups[1].Value } |
        Where-Object { $_ -and $_ -notlike "127.*" } |
        Select-Object -Unique

    $sanParts = @("dns=localhost", "ipaddress=127.0.0.1")
    foreach ($ipAddress in $ipAddresses) {
        $sanParts += "ipaddress=$ipAddress"
    }

    $cert = New-SelfSignedCertificate `
        -Subject "CN=Blind OCR Dev" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -KeyExportPolicy Exportable `
        -NotAfter (Get-Date).AddYears(2) `
        -TextExtension ("2.5.29.17={text}" + ($sanParts -join "&"))

    $securePassword = ConvertTo-SecureString -String $password -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $securePassword | Out-Null

    Write-Host "Created HTTPS certificate: $pfxPath"
    Write-Host "Certificate covers: localhost, 127.0.0.1, $($ipAddresses -join ', ')"
}

$env:VITE_HTTPS = "true"
$env:VITE_HTTPS_CERT_PASSWORD = $password

Set-Location $frontendDir
npm.cmd run dev:lan -- --port 5174

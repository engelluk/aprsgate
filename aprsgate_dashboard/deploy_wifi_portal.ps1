param(
    [Parameter(Mandatory = $true)]
    [string]$Target,

    [string]$RemoteDir = "/tmp/aprsgate_wifi_portal"
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. Install the OpenSSH client or add it to PATH."
    }
}

Require-Command ssh
Require-Command scp

$LocalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SystemdDir = Join-Path $LocalRoot "systemd"

if (-not (Test-Path (Join-Path $LocalRoot "wifi_portal.py"))) {
    throw "wifi_portal.py wurde nicht gefunden."
}
if (-not (Test-Path (Join-Path $LocalRoot "install_wifi_portal.sh"))) {
    throw "install_wifi_portal.sh wurde nicht gefunden."
}
if (-not (Test-Path (Join-Path $LocalRoot "aprsgate_wifi_failover.sh"))) {
    throw "aprsgate_wifi_failover.sh wurde nicht gefunden."
}
if (-not (Test-Path (Join-Path $SystemdDir "aprsgate-wifi-portal.service"))) {
    throw "systemd/aprsgate-wifi-portal.service wurde nicht gefunden."
}
if (-not (Test-Path (Join-Path $SystemdDir "aprsgate-wifi-failover.service"))) {
    throw "systemd/aprsgate-wifi-failover.service wurde nicht gefunden."
}

Write-Host "Creating deployment directory on $Target ..."
ssh $Target "rm -rf '$RemoteDir' && mkdir -p '$RemoteDir/systemd'"

Write-Host "Copying Wi-Fi portal files ..."
scp `
    (Join-Path $LocalRoot "wifi_portal.py") `
    (Join-Path $LocalRoot "aprsgate_wifi_failover.sh") `
    (Join-Path $LocalRoot "install_wifi_portal.sh") `
    (Join-Path $LocalRoot "WIFI_PORTAL.md") `
    "${Target}:${RemoteDir}/"

scp `
    (Join-Path $SystemdDir "aprsgate-wifi-portal.service") `
    (Join-Path $SystemdDir "aprsgate-wifi-failover.service") `
    "${Target}:${RemoteDir}/systemd/"

Write-Host "Installing systemd services on the Pi ..."
ssh -t $Target "cd '$RemoteDir' && chmod +x install_wifi_portal.sh && sudo ./install_wifi_portal.sh && systemctl --no-pager status aprsgate-wifi-portal.service"

Write-Host ""
Write-Host "Done. Setup network details are read from /etc/default/aprsgate-wifi on the Pi."

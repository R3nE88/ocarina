# Renders the social preview image (site/og.png) and the iPhone icon (site/apple-touch-icon.png)
# from tools/og.html and tools/icon.html using headless Microsoft Edge.
# Usage: powershell -ExecutionPolicy Bypass -File tools\build-images.ps1

$root = Split-Path $PSScriptRoot -Parent
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$profileDir = Join-Path $env:TEMP "edge-headless-ocarina"

function Render-Page($html, $png, $size) {
  $url = "file:///" + ((Join-Path $root $html) -replace '\\', '/' -replace ' ', '%20')
  $out = Join-Path $root $png
  & $edge --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 `
    --virtual-time-budget=3000 "--user-data-dir=$profileDir" "--window-size=$size" "--screenshot=$out" $url | Out-Null
  "{0}: {1:N1} KB" -f $png, ((Get-Item $out).Length / 1KB)
}

Render-Page "tools\og.html" "site\og.png" "1200,630"
Render-Page "tools\icon.html" "site\apple-touch-icon.png" "180,180"

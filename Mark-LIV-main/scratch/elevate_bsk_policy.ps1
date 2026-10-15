# elevate_bsk_policy.ps1 — tulis policy ExtensionInstallForcelist utk BrowserSkill
# Dijalankan ELEVATED (UAC) karena key Software\Policies terkunci utk proses normal.
# Idempotent: aman dijalankan berulang.

$ErrorActionPreference = "Continue"

# Chrome — BrowserSkill extension
$chromeKey = "HKCU:\Software\Policies\Google\Chrome\ExtensionInstallForcelist"
New-Item -Path $chromeKey -Force | Out-Null
Set-ItemProperty -Path $chromeKey -Name "1" -Value "hhcmgoofomhgciiibhipgmgkgnoenaoi;https://clients2.google.com/service/update2/crx" -Type String
Write-Host "Chrome policy ditulis: $chromeKey"

# Edge — BrowserSkill extension
$edgeKey = "HKCU:\Software\Policies\Microsoft\Edge\ExtensionInstallForcelist"
New-Item -Path $edgeKey -Force | Out-Null
Set-ItemProperty -Path $edgeKey -Name "1" -Value "emacgiaaaiojkkpkddmmdfhmokgmnikg;https://edge.microsoft.com/extensionwebstorebase/v1/crx" -Type String
Write-Host "Edge policy ditulis: $edgeKey"

# Verifikasi
foreach ($k in @($chromeKey, $edgeKey)) {
    $v = (Get-ItemProperty -Path $k -ErrorAction SilentlyContinue)."1"
    if ($v) { Write-Host "OK  $k -> $v" } else { Write-Host "GAGAL $k" }
}
Write-Host "SELESAI. Tutup lalu buka Chrome/Edge — extension auto-terpasang dari Web Store."

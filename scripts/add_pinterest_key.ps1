# Pinterest secret -> VPS postiz env (one-time helper, 2026-07-18)
# Run: PowerShell me ye file chalao. Secret sirf TUM paste karoge; kahin store nahi hota.
$sec = Read-Host "Pinterest App Secret paste karke Enter dabao"
if ([string]::IsNullOrWhiteSpace($sec)) { Write-Host "Khaali input - cancel."; exit 1 }
$lines = "PINTEREST_CLIENT_ID=1591704`nPINTEREST_CLIENT_SECRET=$sec`n"
$remote = "cd /opt/leadgen/deploy/postiz && cp .env .env.bak.pinterest && cat >> .env && chmod 600 .env && echo APPENDED && grep -c '^PINTEREST' .env"
$lines | & C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 $remote
Write-Host "Agar upar 'APPENDED' aur '2' dikha to ho gaya - Claude ko 'ho gaya' bol do."

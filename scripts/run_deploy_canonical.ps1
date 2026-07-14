# run_deploy_canonical.ps1 — pull, DRY_RUN the canonical script, then run it for real (detached)
param([switch]$DryRunOnly)
$ErrorActionPreference = 'Continue'
$ssh = 'C:\PROGRA~1\Git\usr\bin\ssh.exe'
$key = 'C:\Users\Ratanshila\.ssh\id_rsa'
$host_ = 'root@72.61.245.204'

if ($DryRunOnly) {
  # Pull the script, normalise CRLF, and print the plan without changing anything.
  & $ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=25 $host_ 'cd /opt/leadgen && git pull --ff-only 2>&1 | tail -2 && sed -i "s/\r$//" scripts/deploy_vps.sh && echo "--- DRY RUN ---" && DRY_RUN=1 bash scripts/deploy_vps.sh; echo "DRY_RC=$?"' 2>&1 | Out-String
} else {
  & $ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=25 $host_ 'cd /opt/leadgen && rm -f /tmp/dep.log && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 < /dev/null & sleep 2; echo LAUNCHED' 2>&1 | Out-String
}

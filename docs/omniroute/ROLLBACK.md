# OmniRoute rollback

Rollback snapshot created before inspection:

```text
/root/.omniroute_backups/a2z-20260713T170103Z
```

The snapshot contains the OmniRoute data directory, selected LeadGen integration files,
and `ROLLBACK_MANIFEST.txt`; it is outside the Git working tree and mode-restricted.

```bash
tmux kill-session -t leadgen-omni || true
mv /root/.omniroute /root/.omniroute.pre-a2z-20260713T170103Z
cp -a /root/.omniroute_backups/a2z-20260713T170103Z/omniroute /root/.omniroute
chmod 700 /root/.omniroute
export PATH="/root/.nvm/versions/node/v22.23.1/bin:$PATH"
omniroute
```

For LeadGen, keep `OMNIROUTE_ENABLED=0` (or unset it). No production container,
database, Celery worker, scheduler, or deployed environment change was made in this
phase, so no production rollback is needed.

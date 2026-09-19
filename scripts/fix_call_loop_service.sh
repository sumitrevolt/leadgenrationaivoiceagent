#!/bin/bash
# Fix leadgen-call-loop.service path

cat > /etc/systemd/system/leadgen-call-loop.service << 'SERVICEEOF'
[Unit]
Description=LeadGen platform cold-outbound call loop (TRAI window-aware, Tata SmartFlo)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/leadgen
EnvironmentFile=/opt/leadgen/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/venv/bin/python /opt/leadgen/scripts/fire_calls_loop.py --batch-size 3
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl restart leadgen-call-loop
sleep 3
systemctl status leadgen-call-loop.service

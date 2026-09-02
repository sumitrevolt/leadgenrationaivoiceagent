FROM python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49

COPY --chown=65534:65534 tests/fixtures/dsh_fake_gateway.py /opt/dsh-smoke/gateway.py
USER 65534:65534
EXPOSE 8000
ENTRYPOINT ["python", "/opt/dsh-smoke/gateway.py"]

"""Entry point for the MCP proxy container: ``python -m mcp_proxy``.

Starts the listener with mutual TLS against the root the backend published.
``CERT_REQUIRED`` is the point of the whole file: without it, anything that can
route to this port on the internal network could ask it to launch a command.

The material has to exist before this runs. In ``compose.yml`` that is
guaranteed by ``depends_on: backend: service_healthy`` — the backend writes it
during startup, before it reports healthy — so a missing file here means the
volume is not shared, not that the two raced.
"""

import logging
import ssl
import sys

import uvicorn

from config import get_settings
from infrastructure.logging_context import setup_logging
from infrastructure.mcp_transport_tls import proxy_server_credentials

logger = logging.getLogger(__name__)


def main() -> int:
    """Run the proxy until it is stopped.

    Returns:
        A process exit status: non-zero when the TLS material is missing.
    """
    setup_logging()
    settings = get_settings()
    credentials = proxy_server_credentials()

    missing = [
        str(path)
        for path in (
            credentials.ca_certificate,
            credentials.certificate,
            credentials.private_key,
        )
        if not path.is_file()
    ]
    if missing:
        logger.error(
            "Cannot start: the backend has not published %s. It writes this "
            "directory at startup; check that both containers mount the same "
            "volume and that MCP_PROXY_TLS_DIR agrees on both sides.",
            ", ".join(missing),
        )
        return 1

    uvicorn.run(
        "mcp_proxy.app:app",
        host="0.0.0.0",  # noqa: S104 — the container's own network namespace
        port=settings.mcp_proxy_port,
        ssl_certfile=str(credentials.certificate),
        ssl_keyfile=str(credentials.private_key),
        ssl_ca_certs=str(credentials.ca_certificate),
        # Nothing without a certificate this deployment issued gets to speak.
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        # Keeps the timestamped format setup_logging() installed.
        log_config=None,
        timeout_graceful_shutdown=30,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

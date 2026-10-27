"""Mail sender.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
import ssl
from email.message import EmailMessage

import aiosmtplib

from airthings_bridge.config import SmtpConfig

logger = logging.getLogger(__name__)


class Mailer:
    """Sends mails with the configured SMTP server.

    The server certificate is verified for SSL and TLS (STARTTLS) connections.
    """

    TIMEOUT = 30

    def __init__(self, smtp: SmtpConfig):
        self._smtp = smtp

    async def send(self, from_address: str, to_addresses: list[str], subject: str,
                   message: str) -> None:
        """Send a mail. Raises aiosmtplib.SMTPException or OSError."""
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = ", ".join(to_addresses)
        msg.set_content(message)

        smtp = self._smtp
        login = smtp.user is not None and smtp.password is not None
        await aiosmtplib.send(
            msg, hostname=smtp.server, port=smtp.port,
            username=smtp.user if login else None,
            password=smtp.password if login else None,
            use_tls=smtp.security == "SSL", start_tls=smtp.security == "TLS",
            tls_context=ssl.create_default_context(), timeout=self.TIMEOUT)
        logger.info("Message sent to %s: %s", msg["To"], subject)

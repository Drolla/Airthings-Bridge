"""Alerts: print and mail actions triggered by sensor levels.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
from collections.abc import Callable

from airthings_bridge.config import AlertConfig, MailActionConfig, PrintActionConfig, SmtpConfig
from airthings_bridge.mail import ThreadedSendMail
from airthings_bridge.readings import SensorData
from airthings_bridge.trigger import Trigger

logger = logging.getLogger(__name__)


def _format(message: str, value: float, device: str, sensor: str) -> str:
    return message.replace("%v", str(value)).replace("%d", device).replace("%s", sensor)


class Alerts:
    """Configured alerts, checked with the sensor data of each reading cycle."""

    def __init__(self, alerts: tuple[AlertConfig, ...], smtp: SmtpConfig | None):
        self._mailer = None
        if smtp is not None:
            self._mailer = ThreadedSendMail(
                server=smtp.server, port=smtp.port, security=smtp.security,
                user=smtp.user, password=smtp.password)
        self._triggers = [
            (alert.sources,
             Trigger(alert.trigger, [self._action(action) for action in alert.actions]))
            for alert in alerts]

    def _action(self, action_config: MailActionConfig | PrintActionConfig
                ) -> Callable[[float, str, str], None]:
        if isinstance(action_config, MailActionConfig):
            def mail(value: float, device: str, sensor: str) -> None:
                self._mailer.send_mail(
                    action_config.from_, list(action_config.to), action_config.subject,
                    _format(action_config.message, value, device, sensor))
            return mail

        def log(value: float, device: str, sensor: str) -> None:
            logger.info(_format(action_config.message, value, device, sensor))
        return log

    def check_levels(self, data: SensorData) -> None:
        """Pass the sensor levels to the triggers.

        Raises UserWarning if a source value is not available.
        """
        error_msg = None
        for sources, trigger in self._triggers:
            for device, sensor in sources:
                value = data.get(device, {}).get(sensor)
                if not isinstance(value, int | float):
                    error_msg = f"Data {device}/{sensor} not available"
                    continue
                trigger.log(value, device, sensor)
        if error_msg is not None:
            raise UserWarning(error_msg)

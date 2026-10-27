"""Alerts: print and mail actions triggered by sensor levels.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
from collections.abc import Callable
from typing import Any

from airthings_bridge import trigger
from airthings_bridge.mail import ThreadedSendMail
from airthings_bridge.readings import SensorData

logger = logging.getLogger(__name__)


class PrintAction:
    """Alert action that logs a message.

    The message placeholders %v, %d and %s are replaced by the value, the
    device and the sensor.
    """

    def __init__(self, print_action_config: dict[str, str]):
        self.message = print_action_config.get(
                "message", "Sensor alert: Sensor: %d.%s, Level: %v")

    def action(self, value: float, device: str, sensor: str) -> None:
        """Log the alert message."""
        message = self.message.replace("%v", str(value)).replace("%d", device)\
                              .replace("%s", sensor)
        logger.info(message)


class MailAction:
    """Alert action that sends a mail.

    The message placeholders are the ones of PrintAction.
    """

    def __init__(self, smtp_config: dict[str, Any],
                 mail_action_config: dict[str, Any]):
        self.alert_mail_service = ThreadedSendMail(
                server=smtp_config["server"],
                port=smtp_config.get("port", 587),
                security=smtp_config.get("security"),
                user=smtp_config.get("user"),
                password=smtp_config.get("password"))

        self.from_ = mail_action_config["from"]
        self.to = mail_action_config["to"]
        self.subject = mail_action_config.get("subject", "Sensor alert")
        self.message = mail_action_config.get(
                "message", "Sensor: %d.%s, Level: %v")

    def action(self, value: float, device: str, sensor: str) -> None:
        """Send the alert mail."""
        message = self.message.replace("%v", str(value)).replace("%d", device)\
                              .replace("%s", sensor)
        self.alert_mail_service.send_mail(
                self.from_, self.to, self.subject, message)


class Actions:
    """Alerts defined by the 'smtp_server' and 'alerts' configurations."""

    def __init__(self, smtp_config: dict[str, Any],
                 alerts_config: dict[str, Any] | list[dict[str, Any]]):
        self.sources_trigger_actions_list: \
            list[tuple[list[list[str]], trigger.Trigger]] = []
        for alert_config in (alerts_config if isinstance(alerts_config, list)
                             else [alerts_config]):
            sources = []
            for source in (alert_config["sources"]
                           if isinstance(alert_config["sources"], list)
                           else [alert_config["sources"]]):
                if ":" not in source:
                    raise ValueError(f"Invalid alert source '{source}', "
                                     "expected '<device>:<sensor>'")
                sources.append(source.split(":", 1))

            actions = alert_config["actions"]
            action_functions: list[Callable] = []
            for action in actions if isinstance(actions, list) else [actions]:
                if "mail" in action:
                    action_functions.append(
                            MailAction(smtp_config, action["mail"]).action)
                if "print" in action:
                    action_functions.append(
                            PrintAction(action["print"]).action)

            trigger_action = trigger.Trigger(
                    alert_config["trigger"], action_functions)
            self.sources_trigger_actions_list.append((sources, trigger_action))

    def check_levels(self, data: SensorData) -> None:
        """Pass the sensor levels to the triggers.

        Raises UserWarning if a source value is not available.
        """
        error_msg = None
        for sources, trigger_action in self.sources_trigger_actions_list:
            for device, sensor in sources:
                value = data.get(device, {}).get(sensor)
                if not isinstance(value, int | float):
                    error_msg = f"Data {device}/{sensor} not available"
                    continue
                trigger_action.log(value, device, sensor)
        if error_msg is not None:
            raise UserWarning(error_msg)

"""Alerts: print and mail actions triggered by sensor levels.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from airthings_bridge.config import AlertConfig, MailActionConfig, PrintActionConfig, SmtpConfig
from airthings_bridge.mail import Mailer
from airthings_bridge.readings import Cycle
from airthings_bridge.trigger import Trigger

logger = logging.getLogger(__name__)


def _format(message: str, value: float, device: str, sensor: str) -> str:
    return message.replace("%v", str(value)).replace("%d", device).replace("%s", sensor)


class Alerts:
    """Alerts consumer: checks the sensor levels of each cycle."""

    # Time to finish sending the pending mails when stopped
    STOP_TIMEOUT = Mailer.TIMEOUT

    def __init__(self, alerts: tuple[AlertConfig, ...], smtp: SmtpConfig | None):
        self._mailer = Mailer(smtp) if smtp is not None else None
        self._pending: set[asyncio.Task[None]] = set()
        self._triggers = [
            (alert.sources,
             Trigger(alert.trigger, [self._action(action) for action in alert.actions]))
            for alert in alerts]

    def _action(self, config: MailActionConfig | PrintActionConfig
                ) -> Callable[[float, str, str], None]:
        if isinstance(config, MailActionConfig):
            mailer = self._mailer
            assert mailer is not None  # Ensured by the configuration validation

            def mail(value: float, device: str, sensor: str) -> None:
                self._spawn(mailer.send(config.from_, list(config.to), config.subject,
                                        _format(config.message, value, device, sensor)))
            return mail

        def log(value: float, device: str, sensor: str) -> None:
            logger.info(_format(config.message, value, device, sensor))
        return log

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._pending.add(task)
        task.add_done_callback(self._done)

    def _done(self, task: asyncio.Task[None]) -> None:
        self._pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Failed to send the alert mail: %s", task.exception())

    async def start(self) -> None:
        """Nothing to start."""

    async def handle(self, cycle: Cycle) -> None:
        """Pass the sensor levels to the triggers."""
        values = cycle.values()
        for sources, trigger in self._triggers:
            for device, sensor in sources:
                value = values.get(device, {}).get(sensor)
                if isinstance(value, int | float):
                    trigger.log(value, device, sensor)
                else:
                    logger.warning("Alert source %s:%s not available", device, sensor)

    async def stop(self) -> None:
        """Wait until the pending mails are sent, or cancel them after STOP_TIMEOUT."""
        if self._pending:
            _, pending = await asyncio.wait(set(self._pending), timeout=self.STOP_TIMEOUT)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

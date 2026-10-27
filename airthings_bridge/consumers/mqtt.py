"""MQTT publishing of the sensor data.

Copyright (C) 2023-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import asyncio
import contextlib
import logging
import time
from typing import Any

import aiomqtt

from airthings_bridge.config import MqttConfig
from airthings_bridge.readings import Cycle

logger = logging.getLogger(__name__)


def create_client(config: MqttConfig, will: dict[str, Any] | None = None) -> aiomqtt.Client:
    """Create a client for the configured broker."""
    tls_params = tls_insecure = None
    if config.tls is not None:
        tls = dict(config.tls)
        tls_insecure = tls.pop("insecure", None)
        tls_params = aiomqtt.TLSParameters(**tls)
    auth = config.auth or {}
    return aiomqtt.Client(
        config.host, config.port, identifier=config.client_id,
        username=auth.get("username"), password=auth.get("password"),
        will=aiomqtt.Will(**will) if will else None, tls_params=tls_params,
        tls_insecure=tls_insecure)


class MqttPublisher:
    """MQTT consumer: publishes the selected sensor data of each cycle.

    The topics are <topic>/<device>/<sensor>, <topic>/<device>/status
    (Online/Offline), <topic>/publish_time and <topic>/status (bridge status:
    Online, Offline, or 'Connection lost' as will). All messages are retained.
    A session task keeps the broker connection and reconnects if it is lost.
    Cycles are dropped while the broker is not connected.
    """

    RECONNECT_DELAY = 10
    STOP_TIMEOUT = 5

    def __init__(self, config: MqttConfig):
        self._config = config
        self._status_topic = self._topic("status")
        self._will = config.will or {
            "topic": self._status_topic, "payload": "Connection lost", "retain": True}
        self._client: aiomqtt.Client | None = None
        self._session: asyncio.Task[None] | None = None

    def _topic(self, *parts: str) -> str:
        return "/".join(filter(bool, [self._config.topic, *parts]))

    async def _run_session(self) -> None:
        while True:
            try:
                async with create_client(self._config, self._will) as client:
                    logger.info("Connected to MQTT broker %s", self._config.host)
                    await client.publish(self._status_topic, "Online", qos=2, retain=True)
                    self._client = client
                    # No subscriptions: the iteration only ends by a disconnection
                    async for _ in client.messages:
                        pass
            except aiomqtt.MqttError as err:
                logger.warning("MQTT broker %s: %s. Reconnect in %ss",
                               self._config.host, err, self.RECONNECT_DELAY)
            finally:
                self._client = None
            await asyncio.sleep(self.RECONNECT_DELAY)

    async def start(self) -> None:
        """Start the session task."""
        self._session = asyncio.create_task(self._run_session())

    def _messages(self, cycle: Cycle) -> list[tuple[str, Any]]:
        publish = self._config.publish
        messages = []
        for reading in cycle.readings:
            sensors = publish.get(reading.device, publish.get("*"))
            if sensors is None:
                continue
            values = reading.values_with_time()
            messages.append((self._topic(reading.device, "status"),
                             "Online" if values else "Offline"))
            messages += [(self._topic(reading.device, sensor), value)
                         for sensor, value in values.items()
                         if sensor in sensors or "*" in sensors]
        messages.append((self._topic("publish_time"), int(time.time())))
        return messages

    async def handle(self, cycle: Cycle) -> None:
        """Publish the sensor data of a cycle."""
        client = self._client
        if client is None:
            logger.warning("MQTT broker not connected, sensor data not published")
            return
        for topic, payload in self._messages(cycle):
            await client.publish(topic, payload, retain=True)

    async def stop(self) -> None:
        """Publish the 'Offline' status and disconnect."""
        if self._client is not None:
            try:
                await self._client.publish(self._status_topic, "Offline", qos=2, retain=True,
                                           timeout=self.STOP_TIMEOUT)
            except aiomqtt.MqttError as err:
                logger.warning("Unable to publish the 'Offline' status: %s", err)
        if self._session is not None:
            self._session.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._session
            self._session = None

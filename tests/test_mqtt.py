"""Tests for the MQTT consumer, with an emulated aiomqtt client."""

import asyncio
import time
from unittest import mock

import aiomqtt
import pytest

from airthings_bridge.config import MqttConfig
from airthings_bridge.consumers import mqtt
from airthings_bridge.readings import Cycle, Reading

CONFIG = MqttConfig(host="broker", topic="home", publish={"office": ["co2"], "cellar": "*"})


class _Client:
    """aiomqtt.Client emulation. Connections fail while 'refuse' is set."""

    instances: list["_Client"] = []
    refuse = 0

    def __init__(self, config, will=None):
        self.will = will
        self.published = []
        self.disconnected = asyncio.Event()
        _Client.instances.append(self)

    async def __aenter__(self):
        if _Client.refuse:
            _Client.refuse -= 1
            raise aiomqtt.MqttError("Connection refused")
        return self

    async def __aexit__(self, *args):
        pass

    async def publish(self, topic, payload, qos=0, retain=False, timeout=None):
        self.published.append((topic, payload, qos, retain))

    @property
    def messages(self):
        async def iterate():
            await self.disconnected.wait()
            raise aiomqtt.MqttError("Disconnected")
            yield
        return iterate()


@pytest.fixture(autouse=True)
def emulated_aiomqtt(monkeypatch):
    monkeypatch.setattr(mqtt, "create_client", _Client)
    monkeypatch.setattr(mqtt.MqttPublisher, "RECONNECT_DELAY", 0.01)
    _Client.instances = []
    _Client.refuse = 0


async def _connected(publisher):
    for _ in range(100):
        await asyncio.sleep(0.01)
        if publisher._client is not None:
            return publisher._client
    raise AssertionError("Not connected")


CYCLE = Cycle(1000, (Reading("office", {"co2": 600.0, "voc": 50.0}, 990.6),
                     Reading("cellar", {}), Reading("garage", {"co2": 1.0}, 990)))


def test_publish():
    async def run():
        publisher = mqtt.MqttPublisher(CONFIG)
        await publisher.start()
        client = await _connected(publisher)
        await publisher.handle(CYCLE)
        await publisher.stop()
        return client

    with mock.patch.object(mqtt.time, "time", return_value=1234.5):
        client = asyncio.run(run())
    assert client.will == {"topic": "home/status", "payload": "Connection lost", "retain": True}
    assert client.published == [
        ("home/status", "Online", 2, True),
        ("home/office/status", "Online", 0, True),
        ("home/office/co2", 600.0, 0, True),
        ("home/cellar/status", "Offline", 0, True),
        ("home/publish_time", 1234, 0, True),
        ("home/status", "Offline", 2, True)]


def test_reconnection():
    async def run():
        _Client.refuse = 2
        publisher = mqtt.MqttPublisher(CONFIG)
        await publisher.start()
        first = await _connected(publisher)
        first.disconnected.set()
        await asyncio.sleep(0.05)
        second = await _connected(publisher)
        await publisher.stop()
        return first, second

    first, second = asyncio.run(run())
    assert len(_Client.instances) == 4
    assert first is not second
    assert second.published[0] == ("home/status", "Online", 2, True)


def test_cycles_are_dropped_while_disconnected(caplog):
    async def run():
        _Client.refuse = 1000
        publisher = mqtt.MqttPublisher(CONFIG)
        await publisher.start()
        await publisher.handle(CYCLE)
        await publisher.stop()

    asyncio.run(run())
    assert "not connected" in caplog.text
    assert all(client.published == [] for client in _Client.instances)


def test_create_client(monkeypatch):
    monkeypatch.undo()
    config = MqttConfig(host="broker", port=8883, publish={}, client_id="bridge",
                        auth={"username": "user", "password": "secret"},
                        tls={"ca_certs": "ca.pem", "insecure": True})
    with mock.patch.object(mqtt.aiomqtt, "Client") as client:
        mqtt.create_client(config, {"topic": "status", "payload": "lost"})
    args, kwargs = client.call_args
    assert args == ("broker", 8883)
    assert (kwargs["identifier"], kwargs["username"], kwargs["password"]) == (
        "bridge", "user", "secret")
    assert kwargs["tls_params"].ca_certs == "ca.pem"
    assert kwargs["tls_insecure"] is True
    assert kwargs["will"].topic == "status"


def test_status_topics_without_root_topic():
    publisher = mqtt.MqttPublisher(MqttConfig(host="broker", publish={"*": "*"}))
    with mock.patch.object(mqtt.time, "time", return_value=time.time()):
        topics = [topic for topic, _ in publisher._messages(CYCLE)]
    assert topics[:3] == ["office/status", "office/co2", "office/voc"]
    assert "garage/co2" in topics and "publish_time" in topics

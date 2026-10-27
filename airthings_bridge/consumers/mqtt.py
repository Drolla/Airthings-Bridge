"""MQTT publishing of the sensor data.

Copyright (C) 2023-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
import ssl
import time
from typing import Any

import paho.mqtt.client as mqtt_client

from airthings_bridge.readings import SensorData

logger = logging.getLogger(__name__)


class ThreadedMqttPublisher:
    """Threaded MQTT client to publish messages.

    This class implements a threaded MQTT client and expose a method to publish
    messages. The opened connection to the MQTT broker is persistent.

    The constructor accepts all the connection options provided by the Paho
    MQTT client publish methods 'single' and 'multiple'. In addition to these
    methods, LWT ('will' argument) is properly taken into account by the broker
    since the connection is persistent.

    Args:
        hostname (string): FQDN or IP4 or IP6 address of the broker
        port (integer): Port to connect to the broker on. default=1883
        keepalive (integer): Timeout value for the client in seconds.
                default=60
        bind_address (string): default=""
        client_id (string): MQTT client id to use. If "" (default) or None, the
                Paho library will generate a client id automatically.
        protocol (integer): Defines the MQTT protocol version. Use either
                MQTTv31, MQTTv311 (default) or MQTTv5.
        transport (string): Defines the transport layer that has to be either
                "tcp" (default) or 'websockets'.
        auth (dict): Dict containing authentication parameters for the client:
                auth = {'username':"<username>", 'password':"<password>"}
                Username is required, password is optional and will default to
                None if not provided. Defaults to None, which indicates no
                authentication is to be used.
        tls (dict): Dict containing TLS configuration parameters for the
                client:
                dict = {'ca_certs':"<ca_certs>", 'certfile':"<certfile>",
                        'keyfile':"<keyfile>", 'tls_version':"<tls_version>",
                        'ciphers':"<ciphers">, 'insecure':"<bool>"}
                ca_certs is required, all other parameters are optional and
                will default to None if not provided, which results in the
                client using the default behaviour - see the paho.mqtt.client
                documentation.
                Alternatively, tls input can be an SSLContext object, which
                will be processed using the tls_set_context method.
                Defaults to None, which indicates that TLS should not be used.
        will (dict): Dict containing will parameters for the client:
                will = {'topic': "<topic>", 'payload':"<payload">, 'qos':<qos>,
                        'retain':<retain>}.
                Topic is required, all other parameters are optional and will
                default to None, 0 and False respectively. Defaults to None,
                which indicates no will should be used.
        proxy_args (dict): Dictionary given to the client. Default=None

    Example:
        mqtt_publisher = ThreadedMqttPublisher(
                hostname="test.mosquitto.org",
                port=1883,
                will={'topic': "my_nice_home/office/status",
                      'payload':"Offline"}
        )
        mqtt_publisher.publish_single(
                "my_nice_home/office/status", "Online")
        mqtt_publisher.publish_multiple(
                [{"topic": "status", "payload": "Online"},
                 {"topic": "humidity", "payload": 61.5},
                 {"topic": "temperature", "payload": 18.5}],
                topic_root="my_nice_home/office"
        )
    """

    def __init__(self,
                 hostname: str, port: int = 1883, keepalive: int = 60,
                 bind_address: str = "", client_id: str | None = "",
                 protocol: int = mqtt_client.MQTTv311,
                 transport: str = "tcp",
                 auth: dict[str, str] | None = None,
                 tls: dict[str, Any] | ssl.SSLContext | None = None,
                 will: dict[str, Any] | None = None,
                 proxy_args: dict[str, Any] | None = None):
        self.mqttc: mqtt_client.Client | None = None

        # Create the MQTT client
        mqttc = mqtt_client.Client(
                callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                protocol=protocol,
                transport=transport
        )
        mqttc.enable_logger()
        logger.debug("ThreadedMqttPublisher: Connect to %s", hostname)

        # Apply proxy, authentication, will and TLS configurations: This
        # section is mainly a copy from the 'multiple' method of the Paho MQTT
        # client's publish module.

        if proxy_args is not None:
            mqttc.proxy_set(**proxy_args)

        if auth:
            username = auth.get('username')
            if username:
                mqttc.username_pw_set(username, auth.get('password'))
            else:
                raise KeyError("The 'username' key was not found, this is "
                               "required for auth")

        if will is not None:
            mqttc.will_set(**will)

        if tls is not None:
            if isinstance(tls, dict):
                tls = tls.copy()
                insecure = tls.pop('insecure', False)
                mqttc.tls_set(**tls)
                if insecure:
                    # Must be set *after* the `mqttc.tls_set()` call since it
                    # sets up the SSL context that `mqttc.tls_insecure_set`
                    # alters.
                    mqttc.tls_insecure_set(insecure)
            else:
                # Assume input is SSLContext object
                mqttc.tls_set_context(tls)

        # Define the connection. The connection will be later performed by the
        # network loop that retries creating a connection until the broker
        # responds.
        mqttc.connect_async(
                host=hostname,
                port=port,
                keepalive=keepalive,
                bind_address=bind_address,
        )
        self.mqttc = mqttc

        # Start the loop in another thread.
        mqttc.loop_start()

    def stop(self) -> None:
        """Stop the network thread and the connection.

        Call preferably this function to stop the connection instead of
        deleting the object instance to ensure a controlled disconnection.
        """
        # Ignore this command if the mqttc object is already deleted (=None)
        if self.mqttc is None:
            return

        logger.debug("ThreadedMqttPublisher: Disconnect and stop")
        self.mqttc.disconnect()
        self.mqttc.loop_stop()
        self.mqttc = None

    def __del__(self) -> None:
        self.stop()

    def publish_single(
            self, topic: str, payload: Any = None, qos: int = 0,
            retain: bool = False, properties: Any = None
    ) -> mqtt_client.MQTTMessageInfo:
        """Publish a single message to a broker."""
        logger.debug("  publish_single %s: %s", topic, payload)
        publish_result = self.mqttc.publish(
                topic, payload, qos, retain, properties)
        logger.debug("  -> %s", str(publish_result))
        return publish_result

    def publish_multiple(self, messages: list[dict[str, Any]],
                         topic_root: str = ""
                         ) -> mqtt_client.MQTTMessageInfo | None:
        """Publish multiple messages to a broker.

        Returns the publish result of the last message, or None if no
        message is provided.
        """
        logger.debug("publish_multiple %s: %s", topic_root, str(messages))
        publish_result = None
        for message in messages:
            topic = "/".join(filter(bool, [topic_root, message["topic"]]))
            payload = message["payload"]
            qos = message.get("qos", 0)
            retain = message.get("retain", False)
            prop = message.get("prop")
            publish_result = self.publish_single(
                    topic, payload, qos, retain, prop)
        return publish_result



class MqttPublisher:
    """MQTT publisher of the sensor data, configured by the 'mqtt' section."""

    # Maximum time in seconds to wait on the publication of the 'Offline'
    # status when the publisher is stopped
    STOP_TIMEOUT = 5

    def __init__(self, config: dict[str, Any]):
        self.mqtt_publisher = None

        self.cfg_topic = config.get("topic", "")
        self.cfg_publish = config["publish"]
        self.status_topic = "/".join(filter(bool, [self.cfg_topic, "status"]))
        will = {"topic": self.status_topic, "payload": "Connection lost",
                "retain": True}

        self.mqtt_publisher = ThreadedMqttPublisher(
            hostname=config["host"],
            port=config.get("port", 1883),
            client_id=config.get("client_id"),
            auth=config.get("auth"),
            tls=config.get("tls"),
            will=config.get("will", will)
        )

        # Wait until the thread is created
        time.sleep(1)
        self.mqtt_publisher.publish_single(
            topic=self.status_topic, payload="Online", qos=2, retain=True)

    def stop(self) -> None:
        """Publish the 'Offline' status and disconnect.

        The publisher cannot be restarted.
        """
        if self.mqtt_publisher is None:
            return

        publish_result = self.mqtt_publisher.publish_single(
            topic=self.status_topic, payload="Offline", qos=2, retain=True)
        try:
            publish_result.wait_for_publish(timeout=self.STOP_TIMEOUT)
        except (ValueError, RuntimeError) as err:
            logger.warning("Unable to publish the 'Offline' status: %s", err)

        self.mqtt_publisher.stop()
        self.mqtt_publisher = None

    def __del__(self) -> None:
        self.stop()

    def publish(self, data: SensorData) -> None:
        """Publish the sensor data selected by the 'publish' configuration."""
        mqtt_messages = []
        for device, device_data in data.items():
            if device in self.cfg_publish:
                sensor_filter = self.cfg_publish[device]
            elif "*" in self.cfg_publish:
                sensor_filter = self.cfg_publish["*"]
            else:
                continue

            mqtt_messages.append({
                "topic": "/".join([device, "status"]),
                "payload": "Online" if device_data else "Offline",
                "retain": True
            })

            for sensor, value in device_data.items():
                if sensor not in sensor_filter and                         "*" not in sensor_filter:
                    continue
                mqtt_messages.append({
                    "topic": "/".join([device, sensor]),
                    "payload": value,
                    "retain": True
                })
        mqtt_messages.append({"topic": "publish_time",
                              "payload": int(time.time()),
                              "retain": True})

        self.mqtt_publisher.publish_multiple(
                mqtt_messages, topic_root=self.cfg_topic)

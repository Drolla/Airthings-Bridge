"""Matter bridge: exposes the devices as Matter devices, by a matter.js process.

Copyright (C) 2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from airthings_bridge import __version__
from airthings_bridge.airthings import AirthingsDevice
from airthings_bridge.config import MATTER_VALUES, MatterConfig
from airthings_bridge.errors import BridgeError
from airthings_bridge.readings import Cycle

logger = logging.getLogger(__name__)

JS_DIR = Path(__file__).resolve().parent.parent / "matter_js"

# Matter enumerations
AIR_QUALITY_UNKNOWN, AIR_QUALITY_GOOD, AIR_QUALITY_FAIR, AIR_QUALITY_POOR = 0, 1, 2, 4
UNIT_PPM, UNIT_BQM3 = 0, 7
MEDIUM_AIR = 0
BATTERY_OK, BATTERY_WARNING, BATTERY_CRITICAL = 0, 1, 2
POWER_SOURCE_ACTIVE = 1
USER_REPLACEABLE = 2

# Concentrations: Value key (radon: the configured radon key), cluster, unit
# and factor from the value unit. VOC is passed in ppm instead of ppb, as
# Google Home shows ppb values 1000 times too high, labelled as ppm.
CONCENTRATIONS = (
    ("radon", "radonConcentrationMeasurement", UNIT_BQM3, 1),
    ("co2", "carbonDioxideConcentrationMeasurement", UNIT_PPM, 1),
    ("voc", "totalVolatileOrganicCompoundsConcentrationMeasurement", UNIT_PPM, 0.001),
)

# Google Home shows air quality, pressure, CO2 and VOC of an endpoint as a
# group, and only the values that changed with the last report, the others as
# unknown. Pressure, CO2 and VOC are therefore optional (MATTER_VALUES), so
# that air quality is shown.

# Air quality levels of the Airthings app: Values from which the air quality
# is fair and poor
AIR_QUALITY_LEVELS = {"radon": (100, 150), "co2": (800, 1000), "voc": (250, 2000)}

# Matter limits the length of the basic information strings
MAX_LABEL = 32


def _process_exists(pid: int) -> bool:
    if sys.platform == "win32":
        # os.kill(pid, 0) would send CTRL_C_EVENT on Windows
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32")
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reset_storage(storage: Path) -> list[Path]:
    """Delete the Matter state (pairings, pairing code, identity) and return the deleted paths.

    Raises BridgeError if the bridge uses the storage. The storage directory is kept.
    """
    if not storage.is_dir():
        return []
    entries = sorted(storage.iterdir())
    # matter.js locks a storage with matter.pid, containing the PID and a token
    for pid_file in storage.glob("*/matter.pid"):
        try:
            pid = int(pid_file.read_text(encoding="utf-8").split()[0])
        except (OSError, ValueError, IndexError):
            continue
        if _process_exists(pid):
            raise BridgeError(f"The Matter storage is in use by process {pid}: Stop the bridge "
                              "first")
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return entries


def _exposed(key: str, optional: tuple[str, ...]) -> bool:
    return key not in MATTER_VALUES or key in optional


def clusters(model: type[AirthingsDevice], radon_key: str,
             optional: tuple[str, ...] = ()) -> list[str]:
    """Return the Matter clusters of a device model (matter.js names)."""
    keys = model.value_keys()
    names = ["airQuality"]
    names += [cluster for key, cluster in (("temperature", "temperatureMeasurement"),
                                            ("humidity", "relativeHumidityMeasurement"),
                                            ("pressure", "pressureMeasurement"))
              if key in keys and _exposed(key, optional)]
    names += [cluster for key, cluster, _, _ in CONCENTRATIONS
              if (radon_key if key == "radon" else key) in keys and _exposed(key, optional)]
    if "battery" in keys:
        names.append("powerSource")
    return names


def endpoint(serial: str, name: str, model: type[AirthingsDevice], radon_key: str,
             optional: tuple[str, ...] = ()) -> dict[str, Any]:
    """Return the endpoint of a device: ID, clusters and initial state."""
    names = clusters(model, radon_key, optional)
    state: dict[str, Any] = {
        "bridgedDeviceBasicInformation": {
            "vendorName": "Airthings", "productName": model.PRODUCT_NAME[:MAX_LABEL],
            "nodeLabel": name[:MAX_LABEL], "serialNumber": serial,
            # Has to differ from the serial number
            "uniqueId": hashlib.sha256(serial.encode()).hexdigest()[:MAX_LABEL],
            "reachable": False},
        "airQuality": {"airQuality": AIR_QUALITY_UNKNOWN},
    }
    for _, cluster, unit, _ in CONCENTRATIONS:
        if cluster in names:
            state[cluster] = {"measurementUnit": unit, "measurementMedium": MEDIUM_AIR}
    if "powerSource" in names:
        state["powerSource"] = {
            "status": POWER_SOURCE_ACTIVE, "order": 0, "description": "Battery",
            "batChargeLevel": BATTERY_OK, "batReplacementNeeded": False,
            "batReplaceability": USER_REPLACEABLE,
            # Optional attribute, supported if initialized
            "batPercentRemaining": None}
    return {"id": f"airthings-{serial}", "clusters": names, "state": state}


def air_quality(values: dict[str, Any], radon_key: str) -> int:
    """Return the air quality: the worst level of radon, CO2 and VOC."""
    levels = [AIR_QUALITY_UNKNOWN]
    for key, (fair, poor) in AIR_QUALITY_LEVELS.items():
        value = values.get(radon_key if key == "radon" else key)
        if value is not None:
            levels.append(AIR_QUALITY_POOR if value >= poor else
                          AIR_QUALITY_FAIR if value >= fair else AIR_QUALITY_GOOD)
    return max(levels)


def cluster_state(values: dict[str, Any], radon_key: str,
                  optional: tuple[str, ...] = ()) -> dict[str, Any]:
    """Return the cluster states of the values of a reading (Matter units).

    Missing values aren't changed. Empty values mark the device unreachable.
    The air quality includes the optional values that aren't exposed.
    """
    state: dict[str, Any] = {"bridgedDeviceBasicInformation": {"reachable": bool(values)}}
    if not values:
        return state
    level = air_quality(values, radon_key)
    if level != AIR_QUALITY_UNKNOWN:
        state["airQuality"] = {"airQuality": level}
    if "temperature" in values:
        state["temperatureMeasurement"] = {"measuredValue": round(values["temperature"] * 100)}
    if "humidity" in values:
        state["relativeHumidityMeasurement"] = {"measuredValue": round(values["humidity"] * 100)}
    if "pressure" in values and _exposed("pressure", optional):
        # Unit 0.1 kPa, which is 1 hPa
        state["pressureMeasurement"] = {"measuredValue": round(values["pressure"])}
    for key, cluster, _, factor in CONCENTRATIONS:
        value = values.get(radon_key if key == "radon" else key)
        if value is not None and _exposed(key, optional):
            state[cluster] = {"measuredValue": value * factor}
    if "battery" in values:
        battery = values["battery"]
        level = BATTERY_CRITICAL if battery < 10 else BATTERY_WARNING if battery < 20 \
            else BATTERY_OK
        state["powerSource"] = {"batPercentRemaining": round(battery * 2),
                                "batChargeLevel": level,
                                "batReplacementNeeded": level == BATTERY_CRITICAL}
    return state


# matter.js log line in plain format: date, time, level, facility and message
_LOG_LINE = re.compile(r"\S+ \S+ (DEBUG|INFO|NOTICE|WARN|ERROR|FATAL)\s+(.*)")
_LOG_LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.DEBUG, "NOTICE": logging.INFO,
               "WARN": logging.WARNING, "ERROR": logging.ERROR, "FATAL": logging.CRITICAL}


class MatterBridge:
    """Matter consumer: exposes the devices by a matter.js bridge process.

    The process (matter_js/bridge.mjs) gets the endpoints at its start and the
    cluster states of each cycle, as JSON lines on stdin. It reports its state
    as JSON lines on stdout, and logs to stderr. It goes online with the first
    cluster states, so that the controllers don't get placeholder values. It
    is restarted if it ends unexpectedly, with the last cluster states.
    """

    START_TIMEOUT = 60  # matter.js starts slowly on a Raspberry Pi Zero
    RESTART_DELAY = 10
    STOP_TIMEOUT = 10

    def __init__(self, config: MatterConfig,
                 devices: list[tuple[str, str, type[AirthingsDevice]]]):
        """Initialize the consumer with the devices (serial, name, model)."""
        self._config = config
        exposed = [d for d in devices if "*" in config.devices or d[1] in config.devices]
        self._endpoints = [endpoint(serial, name, model, config.radon, config.values)
                           for serial, name, model in exposed]
        self._ids = {name: f"airthings-{serial}" for serial, name, _ in exposed}
        self._states: dict[str, dict[str, dict[str, Any]]] = {}  # Last states by endpoint
        self._process: asyncio.subprocess.Process | None = None
        self._ready = asyncio.Event()
        self._controllers = 0
        self._pairing: dict[str, str] | None = None  # Pairing codes while not paired
        self._started = False
        self._stopping = False
        self._supervisor: asyncio.Task[None] | None = None

    def _command(self) -> list[str]:
        if not (JS_DIR / "node_modules").is_dir():
            raise BridgeError(f"matter.js is not installed: Run 'npm ci' in {JS_DIR}")
        return [self._config.node, str(JS_DIR / "bridge.mjs")]

    async def _send(self, process: asyncio.subprocess.Process, message: dict[str, Any]) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(message).encode() + b"\n")
        await process.stdin.drain()

    def _init_message(self) -> dict[str, Any]:
        config = self._config
        major, minor, patch = (int(part) for part in __version__.split(".")[:3])
        return {"type": "init", "storage": str(config.storage), "port": config.port,
                "version": __version__, "versionNumber": major * 10000 + minor * 100 + patch,
                "passcode": config.passcode, "discriminator": config.discriminator,
                "logLevel": "debug" if logger.isEnabledFor(logging.DEBUG) else "notice",
                "endpoints": self._endpoints}

    def _handle_message(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "ready":
            self._started = True
            self._ready.set()
        elif kind in ("online", "fabrics"):
            self._controllers = int(message.get("fabrics") or 0)
            if self._controllers:
                self._pairing = None
            logger.info("Matter bridge %s, %s paired controller(s)",
                        "online" if kind == "online" else "pairings changed", self._controllers)
        elif kind == "pairing":
            self._pairing = {"manual": str(message.get("manual")), "qr": str(message.get("qr"))}
            logger.warning("Matter bridge not paired. Manual pairing code: %s, QR code content: %s",
                           self._pairing["manual"], self._pairing["qr"])

    def status(self) -> dict[str, Any]:
        """Return the pairing state (/matter format), with the codes while not paired."""
        status: dict[str, Any] = {"paired": self._controllers > 0,
                                  "controllers": self._controllers}
        if self._pairing is not None:
            status.update(self._pairing)
        return status

    async def _read_stdout(self, stream: asyncio.StreamReader) -> None:
        async for line in stream:
            text = line.decode(errors="replace").rstrip()
            try:
                message = json.loads(text)
            except ValueError:
                message = None
            if isinstance(message, dict):
                self._handle_message(message)
            elif text:
                logger.info("%s", text)

    async def _read_stderr(self, stream: asyncio.StreamReader) -> None:
        # Further lines of a log entry (e.g. a stack trace) get its level
        level = logging.INFO
        async for line in stream:
            text = line.decode(errors="replace").rstrip()
            match = _LOG_LINE.fullmatch(text)
            if match:
                level = _LOG_LEVELS[match.group(1)]
                text = match.group(2)
                # A controller still uses its session of before a restart, harmless
                if "Ignoring message for unknown session" in text:
                    level = min(level, logging.INFO)
            if text:
                logger.log(level, "%s", text)

    async def _run_process(self) -> int | None:
        """Run the bridge process until it ends, and return its exit code."""
        try:
            process = await asyncio.create_subprocess_exec(
                *self._command(), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError:
            raise BridgeError(f"Node.js not found: '{self._config.node}'") from None
        except NotImplementedError:
            # Windows, where aiomqtt requires an event loop without subprocesses
            raise BridgeError("Matter can't be used together with MQTT on Windows") from None
        assert process.stdout is not None and process.stderr is not None
        self._process = process
        try:
            await self._send(process, self._init_message())
            if self._states:
                await self._send(process, {"type": "update", "states": self._states})
            await asyncio.gather(self._read_stdout(process.stdout),
                                 self._read_stderr(process.stderr))
            return await process.wait()
        finally:
            self._process = None
            self._ready.clear()
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def _supervise(self) -> None:
        while True:
            try:
                reason = f"ended with exit code {await self._run_process()}"
            except (BridgeError, OSError) as err:
                if not self._started:
                    raise
                reason = f"failed: {err}"
            if self._stopping:
                return
            if not self._started:
                raise BridgeError(f"Matter bridge process {reason}")
            logger.warning("Matter bridge process %s. Restart in %ss", reason,
                           self.RESTART_DELAY)
            await asyncio.sleep(self.RESTART_DELAY)

    async def start(self) -> None:
        """Start the bridge process and wait until it is ready.

        Raises BridgeError if it can't be started.
        """
        supervisor = self._supervisor = asyncio.create_task(self._supervise())
        ready = asyncio.create_task(self._ready.wait())
        await asyncio.wait({supervisor, ready}, timeout=self.START_TIMEOUT,
                           return_when=asyncio.FIRST_COMPLETED)
        if ready.done():
            return
        ready.cancel()
        if supervisor.done():
            self._supervisor = None
            supervisor.result()  # Raise the start error
        await self.stop()
        raise BridgeError(f"Matter bridge process not ready within {self.START_TIMEOUT}s")

    async def handle(self, cycle: Cycle) -> None:
        """Pass the cluster states of the cycle's readings to the bridge process."""
        process = self._process
        if process is None or not self._ready.is_set():
            logger.warning("Matter bridge process not ready, sensor data not passed")
            return
        config = self._config
        states = {self._ids[reading.device]:
                  cluster_state(reading.values, config.radon, config.values)
                  for reading in cycle.readings if reading.device in self._ids}
        for endpoint_id, state in states.items():
            last = self._states.setdefault(endpoint_id, {})
            for cluster, attributes in state.items():
                last.setdefault(cluster, {}).update(attributes)
        await self._send(process, {"type": "update", "states": states})

    async def stop(self) -> None:
        """Stop the bridge process, which closes its Matter server."""
        self._stopping = True
        process = self._process
        if process is not None and process.returncode is None:
            with contextlib.suppress(OSError):
                await self._send(process, {"type": "stop"})
            try:
                await asyncio.wait_for(process.wait(), self.STOP_TIMEOUT)
            except TimeoutError:
                logger.warning("Matter bridge process didn't stop, killed")
                process.kill()
        if self._supervisor is not None:
            self._supervisor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._supervisor
            self._supervisor = None

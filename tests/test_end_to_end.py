"""End-to-end tests: the bridge with emulated devices and its HTTP interface."""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time

import aiohttp
import pytest

from airthings_bridge.bridge import Bridge
from airthings_bridge.config import build_config

DEVICES = ["2930123456, office", "3250123456, cellar"]


def _config(tmp_path, **changes):
    data = {"sn": DEVICES, "emulation": True, "port": 0, "csv": str(tmp_path / "log.csv"),
            "period": 60, "data_retention": 3600}
    data.update(changes)
    return build_config(data)


async def _with_bridge(config, check):
    """Run the bridge, call check(get) when it serves data, and stop it."""
    bridge = Bridge(config)
    task = asyncio.create_task(bridge.run())
    async with aiohttp.ClientSession() as session:
        async def get(path):
            url = f"http://127.0.0.1:{bridge.web_server.port}{path}"
            async with session.get(url) as response:
                return response.status, await response.text()

        for _ in range(100):
            await asyncio.sleep(0.05)
            if bridge.web_server is not None and bridge.live.as_json()["devices"]:
                break
        try:
            await check(get)
        finally:
            bridge.stop()
            await task
    assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []


def test_http_requests(tmp_path):
    async def check(get):
        status, body = await get("/")
        assert status == 200 and "<title>Airthings Bridge</title>" in body

        status, body = await get("/data")
        devices = json.loads(body)["devices"]
        assert set(devices) == {"office", "cellar"}
        assert {"co2", "radon_st", "update_time"} <= set(devices["office"])
        assert {"radon_week", "radon_year"} <= set(devices["cellar"])

        status, body = await get("/meta")
        meta = json.loads(body)
        assert meta["devices"][1] == {
            "name": "cellar", "serial": "3250123456", "model": "Corentium Home 2",
            "values": ["radon_st", "radon_week", "radon_month", "radon_lt", "temperature",
                       "humidity", "radon_year", "battery"],
            "logged": ["radon_st", "radon_week", "radon_month", "radon_lt", "temperature",
                       "humidity"]}
        assert meta["measurements"][0] == {
            "key": "radon_st", "label": "Radon, 1 day average", "unit": "Bq/m³"}

        status, body = await get("/csv?*:temperature;*:radon_lt")
        lines = body.splitlines()
        assert lines[0] == ("Time,office:temperature,cellar:temperature,"
                            "office:radon_lt,cellar:radon_lt")
        assert len(lines) > 50  # Emulation pre-fills an empty log

        status, body = await get("/csv?re=cellar:radon_.*")
        assert body.splitlines()[0] == ("Time,cellar:radon_st,cellar:radon_week,"
                                        "cellar:radon_month,cellar:radon_lt")
        assert (await get("/csv?re=("))[0] == 400

        assert (await get("/ui/dygraph.min.js"))[0] == 200
        assert (await get("/ui/../server.py"))[0] == 404
        assert (await get("/ui/..%2Fserver.py"))[0] == 404
        assert (await get("/eval?1+1"))[0] == 404

    asyncio.run(_with_bridge(_config(tmp_path), check))


def test_developer_mode(tmp_path):
    async def check(get):
        assert await get("/eval?1+1") == (200, "Result:<br>2")
        assert await get("/eval?len(bridge.devices)") == (200, "Result:<br>2")
        assert (await get("/eval?1/0"))[1].startswith("Error:")

    asyncio.run(_with_bridge(_config(tmp_path, developer=True), check))


def test_without_csv_log(tmp_path):
    async def check(get):
        assert (await get("/csv"))[0] == 404
        meta = json.loads((await get("/meta"))[1])
        assert all(device["logged"] == [] for device in meta["devices"])

    asyncio.run(_with_bridge(_config(tmp_path, csv=None), check))


def test_restart_reloads_the_log(tmp_path):
    async def check(get):
        pass

    asyncio.run(_with_bridge(_config(tmp_path), check))
    records = (tmp_path / "log.csv").read_text().count("\n")

    async def check_reload(get):
        lines = (await get("/csv?*:co2"))[1].splitlines()
        assert len(lines) >= 50

    asyncio.run(_with_bridge(_config(tmp_path), check_reload))
    assert (tmp_path / "log.csv").read_text().count("\n") > records


def test_port_in_use(tmp_path):
    async def run():
        server = await asyncio.start_server(lambda r, w: None, port=0)
        port = server.sockets[0].getsockname()[1]
        try:
            with pytest.raises(OSError):
                await Bridge(_config(tmp_path, port=port, csv=None)).run()
        finally:
            server.close()

    asyncio.run(run())


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM requires POSIX")
def test_sigterm_stops_the_bridge(tmp_path):
    log = tmp_path / "bridge.log"
    process = subprocess.Popen(
        [sys.executable, "-m", "airthings_bridge", *DEVICES, "--emulation", "--port", "0",
         "--csv", str(tmp_path / "log.csv"), "--log", str(log)])
    try:
        for _ in range(100):
            time.sleep(0.1)
            if log.exists() and "Start polling" in log.read_text():
                break
        os.kill(process.pid, signal.SIGTERM)
        assert process.wait(timeout=10) == 0
    finally:
        process.kill()
    assert "Airthings Bridge ended" in log.read_text()

"""Smoke test of the matter.js bridge process (matter_js/bridge.mjs).

Requires Node.js (AIRTHINGS_BRIDGE_NODE or on the path) and the installed
matter.js (npm ci in airthings_bridge/matter_js).
"""

import asyncio
import logging
import os
import shutil

import pytest

from airthings_bridge.bridge import Bridge
from airthings_bridge.config import build_config
from airthings_bridge.consumers import matter

NODE = os.environ.get("AIRTHINGS_BRIDGE_NODE") or shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None or not (matter.JS_DIR / "node_modules").is_dir(),
    reason="Node.js or matter.js not installed")


def test_bridge_process(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger=matter.logger.name)
    config = build_config({
        "sn": ["2930123456, office", "2920123456, cellar", "3250123456, basement"],
        "emulation": True, "period": 1,
        "matter": {"storage": str(tmp_path), "port": 5599, "node": NODE}})

    async def run():
        bridge = Bridge(config)
        asyncio.get_running_loop().call_later(5, bridge.stop)
        await bridge.run()

    asyncio.run(run())
    messages = [r.getMessage() for r in caplog.records]
    assert "Matter bridge ready, 0 paired controller(s)" in messages
    assert any("Manual pairing code" in m for m in messages)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not any("Restart" in m for m in messages)
    assert (tmp_path / "airthings-bridge").is_dir()

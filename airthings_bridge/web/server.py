"""HTTP server: web UI, current sensor data and sensor history.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import fnmatch
import html
import logging
import time
import urllib.parse
from pathlib import Path
from typing import Any

from aiohttp import web

from airthings_bridge.consumers.sensorlog import SensorLog
from airthings_bridge.readings import LiveState

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent / "static"


class WebServer:
    """HTTP server.

    Requests:
       * /: Redirect to /ui/index.html
       * /data: Current sensor data in JSON format
       * /meta: Measurements and devices in JSON format, for the web UI
       * /csv: Sensor data history in CSV format, selected by glob patterns
         separated by ';' (/csv?*:temp*;*:hum*) or by a regular expression
         (/csv?re=...)
       * /ui/<file>: Web UI file
       * /eval?<expression> (developer mode only): Evaluated Python
         expression, with the eval_namespace variables
    """

    def __init__(self, port: int, live: LiveState, meta: dict[str, Any],
                 sensor_log: SensorLog | None, decimations: list[tuple[float, int]],
                 developer: bool = False, eval_namespace: dict[str, Any] | None = None):
        self._port = port
        self._live = live
        self._meta = meta
        self._sensor_log = sensor_log
        self._decimations = decimations
        self._eval_namespace = eval_namespace or {}
        self._runner: web.AppRunner | None = None

        app = web.Application()
        app.router.add_get("/", self._root)
        app.router.add_get("/data", self._data)
        app.router.add_get("/meta", self._meta_data)
        if sensor_log is not None:
            app.router.add_get("/csv", self._csv)
        app.router.add_static("/ui/", UI_DIR)
        if developer:
            app.router.add_get("/eval", self._eval)
        app.on_response_prepare.append(self._allow_cors)
        self._app = app

    @property
    def port(self) -> int:
        """Listening port, assigned by the system if 0 was configured."""
        if self._runner is not None:
            for address in self._runner.addresses:
                return address[1]
        return self._port

    async def start(self) -> None:
        """Start listening. Raises OSError if the port can't be opened."""
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, port=self._port).start()

    async def stop(self) -> None:
        """Close the connections and stop listening."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    @staticmethod
    async def _allow_cors(request: web.Request, response: web.StreamResponse) -> None:
        response.headers["Access-Control-Allow-Origin"] = "*"

    async def _root(self, request: web.Request) -> web.Response:
        raise web.HTTPFound("/ui/index.html")

    async def _data(self, request: web.Request) -> web.Response:
        return web.json_response(self._live.as_json())

    async def _meta_data(self, request: web.Request) -> web.Response:
        return web.json_response(self._meta)

    async def _csv(self, request: web.Request) -> web.Response:
        assert self._sensor_log is not None
        query = urllib.parse.unquote(request.rel_url.raw_query_string)
        patterns: str | list[str]
        if not query:
            patterns = ".*"
        elif query.startswith("re="):
            patterns = query[3:]
        else:
            patterns = [fnmatch.translate(pattern) for pattern in query.split(";")]
        start = time.perf_counter()
        try:
            csv = self._sensor_log.get_csv(patterns, self._decimations)
        except ValueError as err:
            raise web.HTTPBadRequest(text=str(err)) from None
        logger.debug("CSV request %s: %.1f ms", query, 1000 * (time.perf_counter() - start))
        return web.Response(text=csv, content_type="application/csv")

    async def _eval(self, request: web.Request) -> web.Response:
        expression = urllib.parse.unquote(request.rel_url.raw_query_string)
        try:
            result = "Result:<br>" + html.escape(str(eval(expression, self._eval_namespace)))
        except Exception as err:
            result = "Error:<br>" + html.escape(str(err))
        return web.Response(text=result, content_type="text/html")

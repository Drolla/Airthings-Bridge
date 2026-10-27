"""HTTP server: web UI, current sensor data and sensor history.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import fnmatch
import html
import json
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from airthings_bridge.consumers.sensorlog import SensorLog
from airthings_bridge.performancecheck import PerformanceCheck
from airthings_bridge.readings import SensorData

UI_DIR = Path(__file__).resolve().parent / "static"


# A factory function adds the context to the request handler class, see
# https://stackoverflow.com/questions/21631799
def create_http_request_handler(
        all_sensor_data_ts: SensorData,
        log_database: SensorLog | None,
        graph_decimations: list[tuple[float, int]],
        developer: bool) -> type[BaseHTTPRequestHandler]:
    """Create the HTTP request handler class for the provided context."""

    class HttpRequestHandler(BaseHTTPRequestHandler):
        """HTTP request handler.

        Responses:
           * /: Redirect to /ui/index.html
           * /data: Current sensor data in JSON format
           * /csv: Sensor data history in CSV format
           * /ui/<file>: Web UI file
           * /eval?<expression> (developer mode only): Evaluated Python
             expression
        """

        CONTENT_TYPES = {
            '.html': "text/html",
            '.js': "application/javascript",
            '.css': "text/css",
            '': "application/octet-stream",
            }

        def do_GET(self) -> None:
            """Handle the GET requests."""
            http_response = 200
            http_content_type = "text/html"

            if self.path == "/":
                http_body = '<head><meta http-equiv="refresh" ' + \
                            'content="0; URL=/ui/index.html" /></head>'

            elif self.path == "/data":
                http_content_type, http_body = self.get_sensor_data_json()

            elif self.path.startswith("/csv") and log_database is not None:
                try:
                    http_content_type, http_body = \
                            self.get_sensor_history_csv()
                except ValueError as err:
                    http_response = 400
                    http_body = "<h1>400 - Bad request</h1>" + \
                                "<p>" + html.escape(str(err)) + "</p>"

            elif self.path.startswith("/ui/"):
                try:
                    http_content_type, http_body = self.get_file_content()
                except OSError:
                    http_response = 404
                    http_body = "<h1>404 - File not found</h1>"

            elif developer and self.path.startswith("/eval") and \
                    "?" in self.path:
                try:
                    http_content_type, http_body = self.get_eval()
                except Exception as err:
                    http_body = "Error:<br>" + html.escape(str(err))

            else:
                http_response = 404
                http_body = "<h1>404 - Not found</h1>" + \
                            "<p>Allowed requests: /data, /csv, /ui/File</p>"

            self.send_response(http_response)
            self.send_header("Content-type", http_content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if isinstance(http_body, str):
                http_body = http_body.encode("utf8")
            self.wfile.write(http_body)

        def get_sensor_data_json(self) -> tuple[str, str]:
            """Get all sensor data in JSON format."""
            response_raw_data = {
                "current_time": int(time.time()),
                "devices": all_sensor_data_ts
            }
            return "application/json", json.dumps(response_raw_data)

        def get_sensor_history_csv(self) -> tuple[str, str]:
            """Get the sensor history in CSV format.

            The data is selected by glob patterns separated by ';' (e.g.
            /csv?*:temp*;*:hum*), or by a regular expression (/csv?re=...).
            """
            if "?" in self.path:
                device_pattern = urllib.parse.unquote(self.path.split("?")[1])
                if device_pattern[0:3] == "re=":
                    device_pattern = device_pattern[3:]
                else:
                    device_pattern = [fnmatch.translate(dpat)
                                      for dpat in device_pattern.split(";")]
            else:
                device_pattern = ".*"

            with PerformanceCheck("HTTP request, provide sensor data"):
                http_body = log_database.get_csv(
                        device_pattern, graph_decimations)
            return "application/csv", http_body

        def get_file_content(self) -> tuple[str, bytes]:
            """Get the content of a file of the UI directory."""
            file_path = urllib.parse.unquote(self.path.split("?")[0])
            file = (UI_DIR / file_path.removeprefix("/ui/")).resolve()
            if not file.is_relative_to(UI_DIR):
                raise FileNotFoundError(file_path)
            content_type = self.CONTENT_TYPES.get(
                    file.suffix, self.CONTENT_TYPES[""])
            return content_type, file.read_bytes()

        def get_eval(self) -> tuple[str, str]:
            """Evaluate a Python expression."""
            py_function = urllib.parse.unquote(self.path.split("?")[1])
            py_result = eval(py_function)
            return "text/html", "Result:<br>" + html.escape(str(py_result))

        def log_message(self, fmt: str, *args: Any) -> None:
            """Suppress the request logging."""

    return HttpRequestHandler

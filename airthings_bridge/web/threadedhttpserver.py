"""Multi threaded HTTP/web server.

This file implements a multi threaded HTTP/Web server. The port listening and
the request handler for each open socket is executed in an individual daemon
thread.

Copyright (C) 2020 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

from http.server import ThreadingHTTPServer
from socketserver import BaseRequestHandler
from threading import Thread


class ThreadedHTTPServer(ThreadingHTTPServer):
    """Multi threaded HTTP/web server class.

    This HTTP/web server class can be used in the same way as the standard
    class 'HTTPServer', but it generates for the HTTP port listener as well as
    for each HTTP connection a separate thread. This ensures that a main
    application is not affected timing wise by the HTTP server activities, and
    that also the different opened sockets are not interfering.
    """

    daemon_threads = True

    def __init__(self, server_address: tuple[str, int],
                 handler_class: type[BaseRequestHandler]):
        super().__init__(server_address, handler_class)
        thread = Thread(target=self._serve_forever_on_other_thread,
                        daemon=True)
        thread.start()

    def _serve_forever_on_other_thread(self) -> None:
        try:
            self.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.server_close()


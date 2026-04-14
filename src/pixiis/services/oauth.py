"""Browser-based OAuth with local redirect capture.

Starts a temporary HTTP server on localhost, opens the user's browser to the
authorization URL, waits for the redirect callback, and returns the
token/code parameters.  Works with both query-based redirects (Google auth
code) and fragment-based redirects (Twitch implicit grant).
"""

from __future__ import annotations

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


# ── Fragment bridge page ────────────────────────────────────────────────────
# Twitch implicit grant puts the token in the URL *fragment* (#access_token=…)
# which is never sent to the server.  This page extracts the fragment with JS
# and forwards it as a regular query-string GET to /token on the same server.

_FRAGMENT_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Connecting...</title>
<style>
  body { font-family: system-ui, sans-serif; background: #1a1a2e; color: #e0e0e8;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
  .card { text-align: center; padding: 2rem; }
  .ok   { color: #4ade80; font-size: 1.5rem; }
  .fail { color: #f87171; font-size: 1.5rem; }
</style></head><body>
<div class="card" id="msg">Connecting&hellip;</div>
<script>
(function() {
  var hash = window.location.hash.substring(1);
  if (!hash) {
    document.getElementById("msg").innerHTML = '<span class="fail">No token received.</span>';
    return;
  }
  var xhr = new XMLHttpRequest();
  xhr.open("GET", "/token?" + hash, true);
  xhr.onload = function() {
    document.getElementById("msg").innerHTML = '<span class="ok">Connected! You can close this tab.</span>';
  };
  xhr.onerror = function() {
    document.getElementById("msg").innerHTML = '<span class="fail">Failed to send token to app.</span>';
  };
  xhr.send();
})();
</script></body></html>
"""

_SUCCESS_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Done</title>
<style>
  body { font-family: system-ui, sans-serif; background: #1a1a2e; color: #4ade80;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
</style></head><body>
<h2>Connected! You can close this tab.</h2>
</body></html>
"""


class OAuthFlow:
    """Browser-based OAuth with local redirect capture.

    Usage::

        flow = OAuthFlow()
        redirect_uri = f"http://localhost:{flow.port}/callback"
        auth_url = build_auth_url(redirect_uri=redirect_uri)
        flow.start(auth_url)
        result = flow.get_result(timeout=120)
        # result is a dict like {"access_token": "...", "token_type": "bearer"}
    """

    def __init__(self) -> None:
        self._result: dict[str, str] | None = None
        self._event = threading.Event()

        # Bind to a random available port on localhost
        self._server = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The port the local server is listening on."""
        return self._server.server_address[1]

    # ── public API ──────────────────────────────────────────────────────

    def start(self, auth_url: str) -> None:
        """Open the browser and start listening.  Non-blocking."""
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        webbrowser.open(auth_url)

    def get_result(self, timeout: float = 120) -> dict[str, str] | None:
        """Block until the redirect is received or *timeout* seconds elapse.

        Pass ``timeout=0`` for a non-blocking check (returns immediately).
        Returns ``None`` if no result yet or on timeout.
        """
        if timeout <= 0:
            return self._result
        self._event.wait(timeout=timeout)
        return self._result

    def cancel(self) -> None:
        """Shut down the local server early."""
        self._shutdown()

    # ── internals ───────────────────────────────────────────────────────

    def _serve(self) -> None:
        """Run the HTTP server until shut down."""
        self._server.serve_forever()

    def _finish(self, params: dict[str, str]) -> None:
        """Store the result and shut down."""
        self._result = params
        self._event.set()
        # Shut down in a separate thread so the handler can return its response
        threading.Thread(target=self._shutdown, daemon=True).start()

    def _shutdown(self) -> None:
        self._server.shutdown()

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        """Build a request handler class with a reference back to this flow."""
        flow = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)

                if parsed.path == "/callback":
                    qs = parse_qs(parsed.query)
                    flat = {k: v[0] for k, v in qs.items()}
                    if flat:
                        # Query-based redirect (e.g. auth-code flow)
                        self._respond(200, _SUCCESS_HTML)
                        flow._finish(flat)
                    else:
                        # No query params — probably a fragment-based redirect.
                        # Serve the JS bridge page so it can read the fragment.
                        self._respond(200, _FRAGMENT_HTML)

                elif parsed.path == "/token":
                    # Second request from the JS bridge with fragment params
                    qs = parse_qs(parsed.query)
                    flat = {k: v[0] for k, v in qs.items()}
                    self._respond(200, "ok")
                    if flat:
                        flow._finish(flat)

                else:
                    self._respond(404, "Not found")

            def _respond(self, code: int, body: str) -> None:
                self.send_response(code)
                content_type = (
                    "text/html; charset=utf-8"
                    if body.startswith("<!") or body.startswith("<h")
                    else "text/plain"
                )
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                encoded = body.encode("utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                # Suppress console output from the HTTP server
                pass

        return _Handler

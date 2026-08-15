"""
Root-cause fix for "capture stops working every now and then, phone restart
fixes it": WSGIRequestHandler.timeout defaults to None, so a stalled
connection (phone loses signal mid photo-upload) parks its server-side
thread forever. threaded=True means this never crashes anything outright —
it just accumulates one more permanently-blocked thread per stall, until the
tool looks broken. A phone restart was never the actual fix; it just starts a
fresh connection on a fresh thread.

These are structural checks, not a live-socket integration test — actually
reproducing a stalled TCP connection reliably in a unit test is neither cheap
nor necessary to prove the wiring is correct. What matters is: the timeout is
set to a real, finite value, the class is a genuine WSGIRequestHandler
subclass Werkzeug will honor, nothing overrides the setup() method that
applies it, and the real server actually launches with this handler.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from werkzeug.serving import WSGIRequestHandler

import capture_server


def test_bounded_handler_sets_a_real_finite_timeout():
    assert capture_server._BoundedTimeoutRequestHandler.timeout is not None
    assert capture_server._BoundedTimeoutRequestHandler.timeout > 0


def test_bounded_handler_is_a_genuine_wsgi_request_handler_subclass():
    """Werkzeug's run_simple only respects `timeout` on a class it
    recognises as (a subclass of) WSGIRequestHandler."""
    assert issubclass(capture_server._BoundedTimeoutRequestHandler, WSGIRequestHandler)


def test_bounded_handler_does_not_override_setup():
    """setup() is exactly where socketserver.StreamRequestHandler applies
    `self.connection.settimeout(self.timeout)`. Overriding it without
    calling super().setup() would silently disable this fix entirely while
    looking, on the surface, like the timeout is still configured."""
    assert "setup" not in capture_server._BoundedTimeoutRequestHandler.__dict__


def test_the_real_server_launch_uses_the_bounded_handler():
    src = capture_server.__file__
    text = open(src, encoding="utf-8").read()
    run_block = text[text.index('if __name__ == "__main__"'):]
    assert "request_handler=_BoundedTimeoutRequestHandler" in run_block

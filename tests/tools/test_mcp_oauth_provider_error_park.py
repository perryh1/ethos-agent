"""A provider-side OAuth error at the callback parks the server after ONE
browser open.

When the authorization server redirects to the loopback callback with
``error=...`` (``access_denied`` when the user clicks Cancel,
``invalid_request`` for a malformed authorize URL, ``invalid_scope``,
``unauthorized_client``), the callback waiter used to raise a plain
``RuntimeError``. ``_classify_mcp_failure`` treated that as *transient*, so
``run()`` climbed the initial-connect retry ladder — each rung re-running the
SDK's authorization-code grant and opening a fresh browser window — and then
kept doing so on every parked self-probe. In a TTY-attached ``hermes`` session
this looked like "the browser keeps opening new windows".

Now the waiter raises ``OAuthProviderError`` (registered as an auth error, so
the failure is *permanent* and parks at once), and a timed self-probe runs with
interactive OAuth suppressed so it can pick up tokens written by
``hermes mcp login`` without ever opening a browser on its own. Only an
explicit reconnect request re-runs an interactive flow.
"""

import asyncio
import logging
from unittest.mock import MagicMock

import pytest


def _group(*excs) -> BaseExceptionGroup:
    return BaseExceptionGroup("unhandled errors in a TaskGroup", list(excs))


def _interactive_tty_with_display(monkeypatch):
    """Model the environment where the popup storm was observed: a TTY with
    a display, no SSH, no dashboard flow — so the real redirect handler
    really does call ``webbrowser.open``."""
    from tools import mcp_oauth

    stdin = MagicMock()
    stdin.isatty.return_value = True
    monkeypatch.setattr(mcp_oauth.sys, "stdin", stdin)
    monkeypatch.setattr(mcp_oauth, "_can_open_browser", lambda: True)
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    opens: list = []
    monkeypatch.setattr(
        mcp_oauth.webbrowser, "open", lambda url, *a, **kw: opens.append(url) or True
    )
    return opens


@pytest.mark.no_isolate
def test_provider_error_parks_after_one_browser_open(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from tools import mcp_oauth, mcp_tool
    from tools.mcp_oauth import OAuthProviderError
    from tools.mcp_tool import MCPServerTask

    # Tiny self-probe cadence so several probes elapse within the test.
    monkeypatch.setattr(mcp_tool, "_PARKED_RETRY_INTERVAL", 0.05)

    _real_sleep = asyncio.sleep

    async def _fast_sleep(_delay, *a, **kw):
        await _real_sleep(0)

    monkeypatch.setattr(mcp_tool.asyncio, "sleep", _fast_sleep)

    browser_opens = _interactive_tty_with_display(monkeypatch)
    # The REAL redirect handler: it is the thing that opens the browser, and
    # its non-interactive gate is what must stop a timed self-probe.
    redirect_handler = mcp_oauth._make_redirect_handler(port=0)

    state = {"transport_calls": 0, "parks": 0, "authenticated": False}

    async def _wait_until(pred, *, ticks=300, tick=0.01):
        for _ in range(ticks):
            if pred():
                return True
            await _real_sleep(tick)
        return pred()

    async def _scenario():
        class _Task(MCPServerTask):
            def _is_http(self):
                return False

            def _deregister_tools(self):
                state["parks"] += 1
                self._registered_tool_names = []

            async def _run_stdio(self, config):
                state["transport_calls"] += 1
                if state["authenticated"]:
                    # Tokens landed (hermes mcp login): the SDK never calls
                    # the redirect handler; the session simply comes up.
                    self.session = object()
                    await self._wait_for_lifecycle_event()
                    return
                # Mirror the SDK's authorization-code grant: the redirect
                # handler runs first (this is where the browser opens), then
                # the callback waiter reports what the provider answered.
                await redirect_handler("https://auth.example.test/authorize?client_id=x")
                raise _group(
                    OAuthProviderError("invalid_request", "redirect_uri mismatch")
                )

        task = _Task("railway")

        with caplog.at_level(logging.DEBUG, logger="tools.mcp_tool"):
            run_task = asyncio.ensure_future(
                task.run({"command": "x", "auth": "oauth"})
            )

            # 1. The provider refuses: park after ONE attempt / ONE browser open.
            assert await _wait_until(lambda: state["parks"] >= 1), "never parked"
            assert state["transport_calls"] == 1, (
                f"provider error burned {state['transport_calls']} attempts "
                "— it must park immediately, not climb the retry ladder"
            )
            assert len(browser_opens) == 1
            assert not run_task.done(), "run task exited — server is unrevivable"

            # 2. Timed self-probes keep firing but must NOT open the browser:
            #    they run with interactive OAuth suppressed, fail fast on the
            #    redirect handler's non-interactive gate, and re-park.
            assert await _wait_until(lambda: state["transport_calls"] >= 4), (
                f"self-probe never fired (transport_calls={state['transport_calls']})"
            )
            assert len(browser_opens) == 1, (
                f"self-probes opened the browser {len(browser_opens) - 1} more time(s)"
            )
            assert not run_task.done()

            # 3. A deliberate retry (explicit reconnect request: /mcp refresh,
            #    OAuth recovery, a new session's discovery nudge) is still
            #    interactive — the user asked, so the browser opens again.
            task._reconnect_event.set()
            assert await _wait_until(lambda: len(browser_opens) == 2), (
                "explicit reconnect did not re-run the interactive flow"
            )
            # ...and, refused again, it parks again without a storm.
            assert await _wait_until(lambda: state["transport_calls"] >= 7)
            assert len(browser_opens) == 2

            # 4. `hermes mcp login` lands tokens on disk. The next timed
            #    self-probe revives the server from cached tokens with no
            #    browser involvement at all.
            state["authenticated"] = True
            assert await _wait_until(lambda: task.session is not None), (
                "parked server never recovered after re-authentication "
                f"(transport_calls={state['transport_calls']})"
            )
            assert len(browser_opens) == 2

        task._shutdown_event.set()
        task._reconnect_event.set()
        try:
            await asyncio.wait_for(run_task, timeout=15)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            run_task.cancel()

    asyncio.run(_scenario())

    park_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "failed initial authentication" in r.getMessage()
    ]
    # The `hermes mcp login` hint is logged ONCE on the connecting → parked
    # transition (the explicit retry is a fresh transition after a re-park
    # keeps _was_parked set, so it too stays quiet) — not on every probe.
    assert len(park_warnings) == 1, [r.getMessage() for r in park_warnings]
    msg = park_warnings[0].getMessage()
    assert "hermes mcp login railway" in msg
    assert "OAuthProviderError" in msg
    assert "invalid_request" in msg
    assert "redirect_uri mismatch" in msg
    # Re-parks after failed probes are still recorded, at DEBUG.
    reparks = [
        r for r in caplog.records
        if r.levelno == logging.DEBUG
        and "failed initial authentication" in r.getMessage()
    ]
    assert reparks, "failed self-probes were not logged at all"


def test_only_timed_self_probe_wakes_suppress_interactive_oauth(monkeypatch):
    """``_wait_for_reconnect_or_shutdown`` records how the park ended, and
    ``_probe_oauth_policy`` suppresses interactive OAuth only for a timed wake
    on an OAuth server — and only for the one attempt that consumes it."""
    from tools import mcp_oauth
    from tools.mcp_tool import MCPServerTask

    _interactive_tty_with_display(monkeypatch)
    assert mcp_oauth._is_interactive() is True

    task = MCPServerTask("srv")
    task._auth_type = "oauth"

    # Timed wake (nothing set the reconnect event) → unattended probe.
    assert asyncio.run(task._wait_for_reconnect_or_shutdown(timeout=0.01)) == "reconnect"
    assert task._self_probe_wake is True
    with task._probe_oauth_policy():
        assert mcp_oauth._is_interactive() is False
    assert mcp_oauth._is_interactive() is True, "suppression leaked past the attempt"
    assert task._self_probe_wake is False, "flag must be consumed by the attempt"
    with task._probe_oauth_policy():
        assert mcp_oauth._is_interactive() is True

    # Explicit wake → interactive as before.
    task._reconnect_event.set()
    assert asyncio.run(task._wait_for_reconnect_or_shutdown(timeout=5)) == "reconnect"
    assert task._self_probe_wake is False
    assert not task._reconnect_event.is_set()
    with task._probe_oauth_policy():
        assert mcp_oauth._is_interactive() is True

    # Non-OAuth servers have no prompts to suppress: always a no-op.
    task._auth_type = ""
    task._self_probe_wake = True
    with task._probe_oauth_policy():
        assert mcp_oauth._is_interactive() is True
    assert task._self_probe_wake is False

    # Shutdown still wins over everything.
    task._shutdown_event.set()
    assert asyncio.run(task._wait_for_reconnect_or_shutdown(timeout=5)) == "shutdown"

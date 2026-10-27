"""Tests for the mail sender and the alerts consumer."""

import asyncio
import logging
from unittest import mock

import pytest

from airthings_bridge import mail
from airthings_bridge.config import SmtpConfig, build_config
from airthings_bridge.consumers.alerts import Alerts
from airthings_bridge.readings import Cycle, Reading


@pytest.mark.parametrize("security, use_tls, start_tls", [
    ("SSL", True, False), ("TLS", False, True), (None, False, False)])
def test_mail_security(security, use_tls, start_tls):
    smtp = SmtpConfig("mail.home", 465, security, "user", "secret")
    with mock.patch.object(mail.aiosmtplib, "send", mock.AsyncMock()) as send:
        asyncio.run(mail.Mailer(smtp).send("a@home", ["b@home", "c@home"], "Subject", "Text"))
    message = send.call_args.args[0]
    assert (message["From"], message["To"], message["Subject"]) == (
        "a@home", "b@home, c@home", "Subject")
    kwargs = send.call_args.kwargs
    assert (kwargs["hostname"], kwargs["port"]) == ("mail.home", 465)
    assert (kwargs["use_tls"], kwargs["start_tls"]) == (use_tls, start_tls)
    assert (kwargs["username"], kwargs["password"]) == ("user", "secret")


def test_mail_without_login():
    with mock.patch.object(mail.aiosmtplib, "send", mock.AsyncMock()) as send:
        asyncio.run(mail.Mailer(SmtpConfig("mail.home", user="user")).send(
            "a@home", ["b@home"], "Subject", "Text"))
    assert (send.call_args.kwargs["username"], send.call_args.kwargs["password"]) == (
        None, None)


def _alerts(actions):
    config = build_config({
        "sn": "2930123456 office", "smtp_server": {"server": "mail.home"},
        "alerts": {"sources": ["office:radon_st", "office:co2"], "trigger": {"above": 100},
                   "actions": actions}})
    return Alerts(config.alerts, config.smtp)


def _cycle(**values):
    return Cycle(1000, (Reading("office", values, 1000),))


def test_print_alert(caplog):
    async def run():
        alerts = _alerts({"print": {"message": "%d %s: %v"}})
        await alerts.start()
        await alerts.handle(_cycle(radon_st=50, co2=600.0))
        await alerts.handle(_cycle(radon_st=150, co2=600.0))
        await alerts.stop()

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    assert "office radon_st: 150" in caplog.text
    assert "office radon_st: 50" not in caplog.text


def test_mail_alert():
    async def run():
        alerts = _alerts({"mail": {"from": "a@home", "to": "b@home", "message": "%s=%v"}})
        await alerts.handle(_cycle(radon_st=150))
        await alerts.stop()

    with mock.patch.object(mail.Mailer, "send", mock.AsyncMock()) as send:
        asyncio.run(run())
    send.assert_called_once_with("a@home", ["b@home"], "Sensor alert", "radon_st=150")


def test_failed_mail_is_logged(caplog):
    async def run():
        alerts = _alerts({"mail": {"from": "a@home", "to": "b@home"}})
        await alerts.handle(_cycle(radon_st=150))
        await alerts.stop()

    with mock.patch.object(mail.Mailer, "send", mock.AsyncMock(side_effect=OSError("down"))):
        asyncio.run(run())
    assert "Failed to send the alert mail: down" in caplog.text


def test_pending_mails_are_cancelled_after_timeout(monkeypatch):
    monkeypatch.setattr(Alerts, "STOP_TIMEOUT", 0.01)

    async def run():
        alerts = _alerts({"mail": {"from": "a@home", "to": "b@home"}})
        await alerts.handle(_cycle(radon_st=150))
        await alerts.stop()
        return [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    async def slow_send(*args):
        await asyncio.sleep(10)

    with mock.patch.object(mail.Mailer, "send", slow_send):
        assert asyncio.run(run()) == []


def test_missing_source_is_reported(caplog):
    asyncio.run(_alerts({"print": {}}).handle(_cycle(radon_st=50)))
    assert "Alert source office:co2 not available" in caplog.text

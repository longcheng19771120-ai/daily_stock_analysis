# -*- coding: utf-8 -*-
"""Signature verification tests for the DingTalk webhook platform adapter."""

import base64
import hashlib
import hmac
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.platforms.dingtalk import DingtalkPlatform

APP_SECRET = "test-dingtalk-secret"


def _sign(timestamp: str, secret: str = APP_SECRET) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _platform(app_secret):
    config = SimpleNamespace(dingtalk_app_key="key", dingtalk_app_secret=app_secret)
    with patch("src.config.get_config", return_value=config):
        return DingtalkPlatform()


class DingtalkVerifyRequestTestCase(unittest.TestCase):
    def test_valid_signature_is_accepted(self) -> None:
        ts = str(int(time.time() * 1000))
        headers = {"timestamp": ts, "sign": _sign(ts)}
        self.assertTrue(_platform(APP_SECRET).verify_request(headers, b"{}"))

    def test_missing_signature_headers_are_rejected_when_secret_configured(self) -> None:
        platform = _platform(APP_SECRET)
        ts = str(int(time.time() * 1000))
        self.assertFalse(platform.verify_request({}, b"{}"))
        self.assertFalse(platform.verify_request({"timestamp": ts}, b"{}"))
        self.assertFalse(platform.verify_request({"sign": _sign(ts)}, b"{}"))

    def test_wrong_signature_is_rejected(self) -> None:
        ts = str(int(time.time() * 1000))
        headers = {"timestamp": ts, "sign": _sign(ts, secret="other-secret")}
        self.assertFalse(_platform(APP_SECRET).verify_request(headers, b"{}"))

    def test_non_ascii_signature_is_rejected_without_error(self) -> None:
        ts = str(int(time.time() * 1000))
        headers = {"timestamp": ts, "sign": "签名"}
        self.assertFalse(_platform(APP_SECRET).verify_request(headers, b"{}"))

    def test_expired_timestamp_is_rejected(self) -> None:
        ts = str(int((time.time() - 2 * 3600) * 1000))
        headers = {"timestamp": ts, "sign": _sign(ts)}
        self.assertFalse(_platform(APP_SECRET).verify_request(headers, b"{}"))

    def test_without_secret_verification_is_skipped(self) -> None:
        self.assertTrue(_platform(None).verify_request({}, b"{}"))


if __name__ == "__main__":
    unittest.main()

"""
Test suite for the Notification Service (Task 33).

TDD Phase: RED → GREEN → REFACTOR

Tests cover:
- send_setup_alert dispatches FCM message with all required payload fields
- alert payload includes all FR-8 fields:
    instrument, direction, confidence_score, entry_price, sl_price, tp_price,
    r_ratio, reasoning, htf_open, htf_high, htf_low, open_bias,
    time_window, narrative_phase, price_vs_daily_open, price_vs_true_day_open,
    is_killzone
- email fallback triggered when FCM fails
- send_setup_alert returns True on success, False on failure

Validates: Requirements FR-8
"""
from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Path setup — ensure workspace root is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from services.notifications.fcm_service import (
    NotificationService,
    SetupAlertPayload,
    FCMError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_payload() -> SetupAlertPayload:
    """A fully-populated SetupAlertPayload covering all FR-8 required fields."""
    return SetupAlertPayload(
        instrument="EURUSD",
        direction="LONG",
        confidence_score=0.82,
        entry_price=1.1050,
        sl_price=1.1020,
        tp_price=1.1110,
        r_ratio=2.0,
        reasoning=(
            "Price swept the Asian range low at 03:15 NY (London Killzone - "
            "manipulation phase). HTF open bias is bullish. Price is below the "
            "True Day Open with a bullish FVG at discount. Expecting expansion "
            "higher into the NY Killzone toward HTF high at 1.1200."
        ),
        htf_open=1.1000,
        htf_high=1.1200,
        htf_low=1.0900,
        open_bias="BULLISH",
        time_window="LONDON_KILLZONE",
        narrative_phase="MANIPULATION",
        price_vs_daily_open="ABOVE",
        price_vs_true_day_open="BELOW",
        is_killzone=True,
    )


@pytest.fixture
def mock_firebase_app():
    """Patch firebase_admin so tests run without real credentials."""
    with patch("services.notifications.fcm_service.firebase_admin") as mock_fb, \
         patch("services.notifications.fcm_service._fb_credentials") as mock_creds:
        mock_fb.get_app.side_effect = ValueError("no app")  # triggers init
        mock_fb.initialize_app.return_value = MagicMock()
        mock_creds.Certificate.return_value = MagicMock()
        yield mock_fb


@pytest.fixture
def mock_messaging(mock_firebase_app):
    """Patch firebase_admin.messaging so send() is controllable."""
    with patch("services.notifications.fcm_service.messaging") as mock_msg:
        mock_msg.Message.return_value = MagicMock()
        mock_msg.Notification.return_value = MagicMock()
        mock_msg.send.return_value = "projects/test/messages/msg-001"
        yield mock_msg


@pytest.fixture
def notification_service(mock_firebase_app, mock_messaging):
    """Return a NotificationService with mocked Firebase and SMTP."""
    return NotificationService(
        firebase_credentials={"type": "service_account"},
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="alerts@example.com",
        smtp_password="secret",
        from_email="alerts@example.com",
    )


# ---------------------------------------------------------------------------
# TestSetupAlertPayload — data model validation
# ---------------------------------------------------------------------------

class TestSetupAlertPayload:
    """Validate the SetupAlertPayload data model contains all FR-8 fields."""

    def test_payload_has_all_required_fr8_fields(self, valid_payload):
        """Test: SetupAlertPayload has all required FR-8 fields.

        Validates: Requirements FR-8
        """
        required_fields = [
            "instrument",
            "direction",
            "confidence_score",
            "entry_price",
            "sl_price",
            "tp_price",
            "r_ratio",
            "reasoning",
            "htf_open",
            "htf_high",
            "htf_low",
            "open_bias",
            "time_window",
            "narrative_phase",
            "price_vs_daily_open",
            "price_vs_true_day_open",
            "is_killzone",
        ]
        payload_dict = valid_payload.model_dump()
        for field in required_fields:
            assert field in payload_dict, f"Missing required FR-8 field: {field}"

    def test_payload_stores_correct_values(self, valid_payload):
        """Test: SetupAlertPayload stores values correctly.

        Validates: Requirements FR-8
        """
        assert valid_payload.instrument == "EURUSD"
        assert valid_payload.direction == "LONG"
        assert valid_payload.confidence_score == 0.82
        assert valid_payload.entry_price == 1.1050
        assert valid_payload.sl_price == 1.1020
        assert valid_payload.tp_price == 1.1110
        assert valid_payload.r_ratio == 2.0
        assert valid_payload.htf_open == 1.1000
        assert valid_payload.htf_high == 1.1200
        assert valid_payload.htf_low == 1.0900
        assert valid_payload.open_bias == "BULLISH"
        assert valid_payload.time_window == "LONDON_KILLZONE"
        assert valid_payload.narrative_phase == "MANIPULATION"
        assert valid_payload.price_vs_daily_open == "ABOVE"
        assert valid_payload.price_vs_true_day_open == "BELOW"
        assert valid_payload.is_killzone is True

    def test_payload_open_bias_accepts_valid_values(self):
        """Test: open_bias accepts BULLISH, BEARISH, NEUTRAL.

        Validates: Requirements FR-8
        """
        for bias in ("BULLISH", "BEARISH", "NEUTRAL"):
            p = SetupAlertPayload(
                instrument="XAUUSD",
                direction="SHORT",
                confidence_score=0.75,
                entry_price=2000.0,
                sl_price=2010.0,
                tp_price=1980.0,
                r_ratio=2.0,
                reasoning="test",
                htf_open=2005.0,
                htf_high=2020.0,
                htf_low=1990.0,
                open_bias=bias,
                time_window="NY_AM_KILLZONE",
                narrative_phase="EXPANSION",
                price_vs_daily_open="BELOW",
                price_vs_true_day_open="BELOW",
                is_killzone=True,
            )
            assert p.open_bias == bias


# ---------------------------------------------------------------------------
# TestSendSetupAlert — FCM dispatch
# ---------------------------------------------------------------------------

class TestSendSetupAlert:
    """Tests for NotificationService.send_setup_alert FCM dispatch.

    Validates: Requirements FR-8
    """

    def test_send_setup_alert_dispatches_fcm_message(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: send_setup_alert dispatches an FCM message.

        Validates: Requirements FR-8
        """
        result = notification_service.send_setup_alert(
            payload=valid_payload,
            fcm_token="device-token-abc",
        )

        mock_messaging.send.assert_called_once()
        assert result is True

    def test_send_setup_alert_includes_all_required_payload_fields(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: FCM message data includes all required FR-8 payload fields.

        Validates: Requirements FR-8
        """
        notification_service.send_setup_alert(
            payload=valid_payload,
            fcm_token="device-token-abc",
        )

        # Inspect the Message constructed
        message_call_kwargs = mock_messaging.Message.call_args
        assert message_call_kwargs is not None

        # Extract the data dict passed to Message
        call_kwargs = message_call_kwargs.kwargs if message_call_kwargs.kwargs else {}
        call_args = message_call_kwargs.args if message_call_kwargs.args else ()

        # The data dict should be passed as keyword arg 'data'
        data = call_kwargs.get("data", {})

        required_fields = [
            "instrument",
            "direction",
            "confidence_score",
            "entry_price",
            "sl_price",
            "tp_price",
            "r_ratio",
            "reasoning",
            "htf_open",
            "htf_high",
            "htf_low",
            "open_bias",
            "time_window",
            "narrative_phase",
            "price_vs_daily_open",
            "price_vs_true_day_open",
            "is_killzone",
        ]
        for field in required_fields:
            assert field in data, (
                f"Missing required FR-8 field '{field}' in FCM message data"
            )

    def test_send_setup_alert_returns_true_on_success(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: send_setup_alert returns True when FCM send succeeds.

        Validates: Requirements FR-8
        """
        mock_messaging.send.return_value = "projects/test/messages/msg-001"

        result = notification_service.send_setup_alert(
            payload=valid_payload,
            fcm_token="device-token-abc",
        )

        assert result is True

    def test_send_setup_alert_returns_false_on_fcm_failure(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: send_setup_alert returns False when FCM send raises an exception.

        Validates: Requirements FR-8
        """
        mock_messaging.send.side_effect = Exception("FCM connection refused")

        # Patch smtplib so email fallback also fails cleanly
        with patch("services.notifications.fcm_service.smtplib") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.SMTP.return_value.__enter__ = MagicMock(
                return_value=mock_smtp_instance
            )
            mock_smtp.SMTP.return_value.__exit__ = MagicMock(return_value=False)
            mock_smtp_instance.sendmail.side_effect = Exception("SMTP also failed")

            result = notification_service.send_setup_alert(
                payload=valid_payload,
                fcm_token="device-token-abc",
                fallback_email="trader@example.com",
            )

        assert result is False

    def test_send_setup_alert_without_token_returns_false(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: send_setup_alert returns False when no FCM token provided and no fallback.

        Validates: Requirements FR-8
        """
        result = notification_service.send_setup_alert(
            payload=valid_payload,
            fcm_token=None,
            fallback_email=None,
        )

        assert result is False

    def test_send_setup_alert_payload_values_match_input(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: FCM message data values match the input payload exactly.

        Validates: Requirements FR-8
        """
        notification_service.send_setup_alert(
            payload=valid_payload,
            fcm_token="device-token-abc",
        )

        call_kwargs = mock_messaging.Message.call_args.kwargs
        data = call_kwargs.get("data", {})

        assert data["instrument"] == "EURUSD"
        assert data["direction"] == "LONG"
        assert float(data["confidence_score"]) == pytest.approx(0.82)
        assert float(data["entry_price"]) == pytest.approx(1.1050)
        assert float(data["sl_price"]) == pytest.approx(1.1020)
        assert float(data["tp_price"]) == pytest.approx(1.1110)
        assert float(data["r_ratio"]) == pytest.approx(2.0)
        assert float(data["htf_open"]) == pytest.approx(1.1000)
        assert float(data["htf_high"]) == pytest.approx(1.1200)
        assert float(data["htf_low"]) == pytest.approx(1.0900)
        assert data["open_bias"] == "BULLISH"
        assert data["time_window"] == "LONDON_KILLZONE"
        assert data["narrative_phase"] == "MANIPULATION"
        assert data["price_vs_daily_open"] == "ABOVE"
        assert data["price_vs_true_day_open"] == "BELOW"
        assert data["is_killzone"] in ("True", "true", True, "1", 1)


# ---------------------------------------------------------------------------
# TestEmailFallback — SMTP fallback when FCM fails
# ---------------------------------------------------------------------------

class TestEmailFallback:
    """Tests for email fallback behaviour when FCM fails.

    Validates: Requirements FR-8
    """

    def test_email_fallback_triggered_when_fcm_fails(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: email fallback is triggered when FCM raises an exception.

        Validates: Requirements FR-8
        """
        mock_messaging.send.side_effect = FCMError("FCM unavailable")

        with patch("services.notifications.fcm_service.smtplib") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.SMTP.return_value.__enter__ = MagicMock(
                return_value=mock_smtp_instance
            )
            mock_smtp.SMTP.return_value.__exit__ = MagicMock(return_value=False)

            result = notification_service.send_setup_alert(
                payload=valid_payload,
                fcm_token="device-token-abc",
                fallback_email="trader@example.com",
            )

            # SMTP sendmail must have been called
            mock_smtp_instance.sendmail.assert_called_once()

    def test_email_fallback_returns_true_on_smtp_success(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: send_setup_alert returns True when FCM fails but email succeeds.

        Validates: Requirements FR-8
        """
        mock_messaging.send.side_effect = FCMError("FCM unavailable")

        with patch("services.notifications.fcm_service.smtplib") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.SMTP.return_value.__enter__ = MagicMock(
                return_value=mock_smtp_instance
            )
            mock_smtp.SMTP.return_value.__exit__ = MagicMock(return_value=False)
            mock_smtp_instance.sendmail.return_value = {}

            result = notification_service.send_setup_alert(
                payload=valid_payload,
                fcm_token="device-token-abc",
                fallback_email="trader@example.com",
            )

        assert result is True

    def test_email_fallback_not_triggered_when_fcm_succeeds(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: email fallback is NOT triggered when FCM succeeds.

        Validates: Requirements FR-8
        """
        mock_messaging.send.return_value = "projects/test/messages/msg-001"

        with patch("services.notifications.fcm_service.smtplib") as mock_smtp:
            notification_service.send_setup_alert(
                payload=valid_payload,
                fcm_token="device-token-abc",
                fallback_email="trader@example.com",
            )

            # SMTP should NOT have been called
            mock_smtp.SMTP.assert_not_called()

    def test_email_fallback_not_triggered_when_no_fallback_email(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: email fallback is skipped when fallback_email is None.

        Validates: Requirements FR-8
        """
        mock_messaging.send.side_effect = FCMError("FCM unavailable")

        with patch("services.notifications.fcm_service.smtplib") as mock_smtp:
            result = notification_service.send_setup_alert(
                payload=valid_payload,
                fcm_token="device-token-abc",
                fallback_email=None,
            )

            mock_smtp.SMTP.assert_not_called()

        assert result is False

    def test_email_subject_contains_instrument_and_direction(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: email subject contains instrument and direction for easy identification.

        Validates: Requirements FR-8
        """
        mock_messaging.send.side_effect = FCMError("FCM unavailable")

        with patch("services.notifications.fcm_service.smtplib") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.SMTP.return_value.__enter__ = MagicMock(
                return_value=mock_smtp_instance
            )
            mock_smtp.SMTP.return_value.__exit__ = MagicMock(return_value=False)

            notification_service.send_setup_alert(
                payload=valid_payload,
                fcm_token="device-token-abc",
                fallback_email="trader@example.com",
            )

            sendmail_args = mock_smtp_instance.sendmail.call_args
            # Third arg is the email body/message string
            email_message = sendmail_args[0][2]
            assert "EURUSD" in email_message
            assert "LONG" in email_message

    def test_email_body_includes_all_key_trade_details(
        self, notification_service, mock_messaging, valid_payload
    ):
        """Test: email body includes entry, SL, TP, confidence, and reasoning.

        Validates: Requirements FR-8
        """
        mock_messaging.send.side_effect = FCMError("FCM unavailable")

        with patch("services.notifications.fcm_service.smtplib") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.SMTP.return_value.__enter__ = MagicMock(
                return_value=mock_smtp_instance
            )
            mock_smtp.SMTP.return_value.__exit__ = MagicMock(return_value=False)

            notification_service.send_setup_alert(
                payload=valid_payload,
                fcm_token="device-token-abc",
                fallback_email="trader@example.com",
            )

            sendmail_args = mock_smtp_instance.sendmail.call_args
            raw_message = sendmail_args[0][2]

            # Decode the MIME message to get the plain-text body
            import email
            import base64
            msg = email.message_from_string(raw_message)
            payload = msg.get_payload(decode=True)
            if payload is not None:
                body = payload.decode("utf-8")
            else:
                body = msg.get_payload()

            # Key trade details must appear in the decoded email body
            assert "1.1050" in body   # entry_price
            assert "1.1020" in body   # sl_price
            assert "1.1110" in body   # tp_price
            assert "0.82" in body     # confidence_score


# ---------------------------------------------------------------------------
# TestNotificationServiceInit — constructor and Firebase init
# ---------------------------------------------------------------------------

class TestNotificationServiceInit:
    """Tests for NotificationService initialisation.

    Validates: Requirements FR-8
    """

    def test_service_initialises_without_error(self, mock_firebase_app):
        """Test: NotificationService can be instantiated without raising.

        Validates: Requirements FR-8
        """
        svc = NotificationService(
            firebase_credentials={"type": "service_account"},
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="alerts@example.com",
            smtp_password="secret",
            from_email="alerts@example.com",
        )
        assert svc is not None

    def test_service_initialises_firebase_app(self, mock_firebase_app):
        """Test: NotificationService initialises the Firebase app on construction.

        Validates: Requirements FR-8
        """
        NotificationService(
            firebase_credentials={"type": "service_account"},
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="alerts@example.com",
            smtp_password="secret",
            from_email="alerts@example.com",
        )

        mock_firebase_app.initialize_app.assert_called_once()

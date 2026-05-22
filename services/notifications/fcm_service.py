"""Notification Service — FCM push alerts with SMTP email fallback.

Responsibilities:
  1. Build a complete FCM alert payload containing all FR-8 required fields.
  2. Dispatch the alert via firebase-admin SDK.
  3. Fall back to SMTP email when FCM fails and a fallback address is provided.

Required alert fields (FR-8):
  instrument, direction, confidence_score, entry_price, sl_price, tp_price,
  r_ratio, reasoning, htf_open, htf_high, htf_low, open_bias,
  time_window, narrative_phase, price_vs_daily_open, price_vs_true_day_open,
  is_killzone

Public API:
  SetupAlertPayload  — Pydantic model for all FR-8 alert fields
  NotificationService — send_setup_alert(payload, fcm_token, fallback_email) -> bool
  FCMError           — raised when FCM send fails

Validates: Requirements FR-8
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from typing import Optional

import firebase_admin
import firebase_admin.credentials as _fb_credentials
import firebase_admin.messaging as messaging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

__all__ = [
    "SetupAlertPayload",
    "NotificationService",
    "FCMError",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FCMError(Exception):
    """Raised when the Firebase Cloud Messaging send call fails."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class SetupAlertPayload(BaseModel):
    """All FR-8 required fields for a trade setup alert.

    Every field maps directly to a key in the FCM message data dict and the
    email body so that downstream consumers (mobile app, email client) receive
    a complete, self-contained alert.

    Validates: Requirements FR-8
    """

    # ── Core setup fields ──────────────────────────────────────────────────
    instrument: str
    """Trading instrument, e.g. 'EURUSD', 'XAUUSD'."""

    direction: str
    """Trade direction: 'LONG' or 'SHORT'."""

    confidence_score: float
    """Confluence score in [0.0, 1.0]."""

    entry_price: float
    """Recommended entry price."""

    sl_price: float
    """Stop-loss price."""

    tp_price: float
    """Take-profit price (TP1)."""

    r_ratio: float
    """Risk-to-reward ratio (TP distance / SL distance)."""

    reasoning: str
    """Human-readable trade reasoning from the 3-question narrative framework."""

    # ── HTF projection levels ──────────────────────────────────────────────
    htf_open: float
    """HTF candle open — directional bias anchor."""

    htf_high: float
    """HTF candle high — upper range boundary / rejection zone."""

    htf_low: float
    """HTF candle low — lower range boundary / support zone."""

    open_bias: str
    """Price position relative to HTF open: 'BULLISH', 'BEARISH', or 'NEUTRAL'."""

    # ── Time window fields (FR-3A) ─────────────────────────────────────────
    time_window: str
    """ICT time window, e.g. 'LONDON_KILLZONE', 'NY_AM_SILVER_BULLET'."""

    narrative_phase: str
    """Market narrative phase: 'ACCUMULATION', 'MANIPULATION', 'EXPANSION', etc."""

    price_vs_daily_open: str
    """Price vs daily open: 'ABOVE', 'BELOW', or 'AT'."""

    price_vs_true_day_open: str
    """Price vs true day open (00:00 NY): 'ABOVE', 'BELOW', or 'AT'."""

    is_killzone: bool
    """True when the time window is a killzone or silver bullet window."""


# ---------------------------------------------------------------------------
# Notification Service
# ---------------------------------------------------------------------------

class NotificationService:
    """Dispatch trade setup alerts via FCM with SMTP email fallback.

    Usage::

        svc = NotificationService(
            firebase_credentials={"type": "service_account", ...},
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_user="alerts@example.com",
            smtp_password="secret",
            from_email="alerts@example.com",
        )
        ok = svc.send_setup_alert(payload, fcm_token="device-token", fallback_email="trader@example.com")

    Validates: Requirements FR-8
    """

    def __init__(
        self,
        firebase_credentials: dict,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_email: str,
    ) -> None:
        """Initialise the service and the Firebase app.

        Args:
            firebase_credentials: Firebase service-account credentials dict.
            smtp_host:            SMTP server hostname.
            smtp_port:            SMTP server port (typically 587 for STARTTLS).
            smtp_user:            SMTP authentication username.
            smtp_password:        SMTP authentication password.
            from_email:           Sender address used in fallback emails.
        """
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_email = from_email

        # Initialise Firebase app (idempotent — skip if already initialised)
        try:
            firebase_admin.get_app()
        except ValueError:
            cred = _fb_credentials.Certificate(firebase_credentials)
            firebase_admin.initialize_app(cred)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_setup_alert(
        self,
        payload: SetupAlertPayload,
        fcm_token: Optional[str] = None,
        fallback_email: Optional[str] = None,
    ) -> bool:
        """Send a trade setup alert via FCM, falling back to email on failure.

        Args:
            payload:        Fully-populated SetupAlertPayload (all FR-8 fields).
            fcm_token:      FCM device registration token.  Required for FCM dispatch.
            fallback_email: Email address to use when FCM fails.  If None, no
                            fallback is attempted.

        Returns:
            True  — alert delivered (via FCM or email fallback).
            False — all delivery attempts failed.

        Validates: Requirements FR-8
        """
        if fcm_token is None and fallback_email is None:
            logger.warning(
                "send_setup_alert: no FCM token and no fallback email — cannot deliver alert"
            )
            return False

        # ── Attempt FCM dispatch ───────────────────────────────────────────
        if fcm_token is not None:
            try:
                self._send_fcm(payload, fcm_token)
                logger.info(
                    "send_setup_alert: FCM alert dispatched for %s %s (confidence=%.2f)",
                    payload.instrument,
                    payload.direction,
                    payload.confidence_score,
                )
                return True
            except Exception as exc:
                logger.warning(
                    "send_setup_alert: FCM failed (%s) — attempting email fallback", exc
                )

        # ── Email fallback ─────────────────────────────────────────────────
        if fallback_email is not None:
            try:
                self._send_email(payload, fallback_email)
                logger.info(
                    "send_setup_alert: email fallback delivered to %s", fallback_email
                )
                return True
            except Exception as exc:
                logger.error("send_setup_alert: email fallback also failed: %s", exc)

        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_fcm_data(self, payload: SetupAlertPayload) -> dict:
        """Convert SetupAlertPayload to a flat string-keyed FCM data dict.

        FCM data values must all be strings.  Numeric and boolean fields are
        converted with str() so the mobile client can parse them.

        Validates: Requirements FR-8
        """
        return {
            # Core setup fields
            "instrument": payload.instrument,
            "direction": payload.direction,
            "confidence_score": str(payload.confidence_score),
            "entry_price": str(payload.entry_price),
            "sl_price": str(payload.sl_price),
            "tp_price": str(payload.tp_price),
            "r_ratio": str(payload.r_ratio),
            "reasoning": payload.reasoning,
            # HTF projection levels
            "htf_open": str(payload.htf_open),
            "htf_high": str(payload.htf_high),
            "htf_low": str(payload.htf_low),
            "open_bias": payload.open_bias,
            # Time window fields
            "time_window": payload.time_window,
            "narrative_phase": payload.narrative_phase,
            "price_vs_daily_open": payload.price_vs_daily_open,
            "price_vs_true_day_open": payload.price_vs_true_day_open,
            "is_killzone": str(payload.is_killzone),
        }

    def _send_fcm(self, payload: SetupAlertPayload, fcm_token: str) -> None:
        """Build and send an FCM message.

        Raises:
            FCMError: if firebase_admin.messaging.send() raises any exception.

        Validates: Requirements FR-8
        """
        data = self._build_fcm_data(payload)

        notification = messaging.Notification(
            title=f"🔔 {payload.instrument} {payload.direction} Setup",
            body=(
                f"Confidence: {payload.confidence_score:.0%} | "
                f"Entry: {payload.entry_price} | "
                f"SL: {payload.sl_price} | "
                f"TP: {payload.tp_price} | "
                f"R: {payload.r_ratio:.1f}R"
            ),
        )

        message = messaging.Message(
            notification=notification,
            data=data,
            token=fcm_token,
        )

        try:
            messaging.send(message)
        except Exception as exc:
            raise FCMError(str(exc)) from exc

    def _build_email_body(self, payload: SetupAlertPayload) -> str:
        """Build a plain-text email body containing all key trade details.

        Uses only ASCII characters to avoid base64 encoding in the MIME message,
        keeping the raw sendmail string human-readable and easily testable.

        Validates: Requirements FR-8
        """
        return (
            f"AgentICTrader.AI - Trade Setup Alert\n"
            f"{'=' * 50}\n\n"
            f"Instrument:          {payload.instrument}\n"
            f"Direction:           {payload.direction}\n"
            f"Confidence Score:    {payload.confidence_score:.4f}\n\n"
            f"Entry Price:         {payload.entry_price:.4f}\n"
            f"Stop Loss:           {payload.sl_price:.4f}\n"
            f"Take Profit:         {payload.tp_price:.4f}\n"
            f"R Ratio:             {payload.r_ratio:.2f}\n\n"
            f"HTF Open:            {payload.htf_open:.4f}\n"
            f"HTF High:            {payload.htf_high:.4f}\n"
            f"HTF Low:             {payload.htf_low:.4f}\n"
            f"Open Bias:           {payload.open_bias}\n\n"
            f"Time Window:         {payload.time_window}\n"
            f"Narrative Phase:     {payload.narrative_phase}\n"
            f"Price vs Daily Open: {payload.price_vs_daily_open}\n"
            f"Price vs True Day:   {payload.price_vs_true_day_open}\n"
            f"Is Killzone:         {payload.is_killzone}\n\n"
            f"Reasoning:\n{payload.reasoning}\n"
        )

    def _send_email(self, payload: SetupAlertPayload, to_email: str) -> None:
        """Send a fallback email via SMTP STARTTLS.

        Raises:
            smtplib.SMTPException: on any SMTP error.

        Validates: Requirements FR-8
        """
        subject = (
            f"[AgentICTrader] {payload.instrument} {payload.direction} Setup "
            f"- Confidence {payload.confidence_score:.0%}"
        )
        body = self._build_email_body(payload)

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._from_email
        msg["To"] = to_email

        with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
            server.starttls()
            server.login(self._smtp_user, self._smtp_password)
            server.sendmail(self._from_email, to_email, msg.as_string())

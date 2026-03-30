"""SMTP backend abstraction layer.

Provides a unified async interface for sending emails through different
providers: direct SMTP relay, Amazon SES, Mailgun, and SendGrid.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import random
import threading
import time
from collections import deque
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


class SmtpBackend(abc.ABC):
    """Abstract base class for all mail-sending backends."""

    @abc.abstractmethod
    async def send(
        self,
        from_addr: str,
        from_name: str | None,
        to_addr: str,
        subject: str,
        body_html: str,
        body_text: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        """Send a single email.  Returns True on success, False on failure."""

    @abc.abstractmethod
    async def test_connection(self) -> bool:
        """Verify that the backend is reachable and credentials are valid."""


# ---------------------------------------------------------------------------
# Standard SMTP / SMTPS relay
# ---------------------------------------------------------------------------

class SmtpRelayBackend(SmtpBackend):
    """Send mail through a standard SMTP or SMTPS relay using aiosmtplib."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.use_ssl = use_ssl

    def _build_message(
        self,
        from_addr: str,
        from_name: str | None,
        to_addr: str,
        subject: str,
        body_html: str,
        body_text: str,
        headers: dict[str, str] | None = None,
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
        msg["To"] = to_addr

        if headers:
            for key, value in headers.items():
                msg[key] = value

        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        return msg

    async def send(
        self,
        from_addr: str,
        from_name: str | None,
        to_addr: str,
        subject: str,
        body_html: str,
        body_text: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        import aiosmtplib

        msg = self._build_message(
            from_addr, from_name, to_addr, subject, body_html, body_text, headers,
        )

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=self.use_tls and not self.use_ssl,
                use_tls=self.use_ssl,
                timeout=30,
            )
            return True
        except aiosmtplib.SMTPException:
            logger.exception("SMTP relay send failed for %s", to_addr)
            return False
        except Exception:
            logger.exception("Unexpected error sending via SMTP relay to %s", to_addr)
            return False

    async def test_connection(self) -> bool:
        import aiosmtplib

        try:
            smtp = aiosmtplib.SMTP(
                hostname=self.host,
                port=self.port,
                start_tls=self.use_tls and not self.use_ssl,
                use_tls=self.use_ssl,
                timeout=15,
            )
            await smtp.connect()
            if self.username and self.password:
                await smtp.login(self.username, self.password)
            await smtp.quit()
            return True
        except Exception:
            logger.exception("SMTP relay connection test failed")
            return False


# ---------------------------------------------------------------------------
# Amazon SES
# ---------------------------------------------------------------------------

class SesBackend(SmtpBackend):
    """Send mail via Amazon SES using boto3."""

    def __init__(
        self,
        region: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        self.region = region
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key

    def _get_client(self):
        import boto3

        kwargs: dict[str, Any] = {"region_name": self.region}
        if self.aws_access_key_id and self.aws_secret_access_key:
            kwargs["aws_access_key_id"] = self.aws_access_key_id
            kwargs["aws_secret_access_key"] = self.aws_secret_access_key
        return boto3.client("ses", **kwargs)

    async def send(
        self,
        from_addr: str,
        from_name: str | None,
        to_addr: str,
        subject: str,
        body_html: str,
        body_text: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        import asyncio

        source = f"{from_name} <{from_addr}>" if from_name else from_addr
        body: dict[str, Any] = {
            "Html": {"Charset": "UTF-8", "Data": body_html},
        }
        if body_text:
            body["Text"] = {"Charset": "UTF-8", "Data": body_text}

        try:
            client = self._get_client()
            # boto3 is synchronous; run in executor to avoid blocking the loop.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: client.send_email(
                    Source=source,
                    Destination={"ToAddresses": [to_addr]},
                    Message={
                        "Subject": {"Charset": "UTF-8", "Data": subject},
                        "Body": body,
                    },
                ),
            )
            return True
        except Exception:
            logger.exception("SES send failed for %s", to_addr)
            return False

    async def test_connection(self) -> bool:
        import asyncio

        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: client.get_send_quota(),
            )
            return True
        except Exception:
            logger.exception("SES connection test failed")
            return False


# ---------------------------------------------------------------------------
# Mailgun HTTP API
# ---------------------------------------------------------------------------

class MailgunBackend(SmtpBackend):
    """Send mail via the Mailgun HTTP API."""

    def __init__(
        self,
        api_key: str,
        domain: str,
        base_url: str = "https://api.mailgun.net/v3",
    ) -> None:
        self.api_key = api_key
        self.domain = domain
        self.base_url = base_url.rstrip("/")

    async def send(
        self,
        from_addr: str,
        from_name: str | None,
        to_addr: str,
        subject: str,
        body_html: str,
        body_text: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        import httpx

        sender = f"{from_name} <{from_addr}>" if from_name else from_addr
        data: dict[str, str] = {
            "from": sender,
            "to": to_addr,
            "subject": subject,
            "html": body_html,
        }
        if body_text:
            data["text"] = body_text

        # Mailgun custom headers are passed as h:Header-Name keys.
        if headers:
            for key, value in headers.items():
                data[f"h:{key}"] = value

        url = f"{self.base_url}/{self.domain}/messages"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    auth=("api", self.api_key),
                    data=data,
                )
                if resp.status_code in (200, 201):
                    return True
                logger.error(
                    "Mailgun API returned %d for %s: %s",
                    resp.status_code, to_addr, resp.text,
                )
                return False
        except Exception:
            logger.exception("Mailgun send failed for %s", to_addr)
            return False

    async def test_connection(self) -> bool:
        import httpx

        url = f"{self.base_url}/{self.domain}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, auth=("api", self.api_key))
                return resp.status_code == 200
        except Exception:
            logger.exception("Mailgun connection test failed")
            return False


# ---------------------------------------------------------------------------
# SendGrid HTTP API
# ---------------------------------------------------------------------------

class SendGridBackend(SmtpBackend):
    """Send mail via the SendGrid v3 Mail Send API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.sendgrid.com",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def send(
        self,
        from_addr: str,
        from_name: str | None,
        to_addr: str,
        subject: str,
        body_html: str,
        body_text: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        import httpx

        from_obj: dict[str, str] = {"email": from_addr}
        if from_name:
            from_obj["name"] = from_name

        content: list[dict[str, str]] = []
        if body_text:
            content.append({"type": "text/plain", "value": body_text})
        content.append({"type": "text/html", "value": body_html})

        payload: dict[str, Any] = {
            "personalizations": [{"to": [{"email": to_addr}]}],
            "from": from_obj,
            "subject": subject,
            "content": content,
        }
        if headers:
            payload["headers"] = headers

        url = f"{self.base_url}/v3/mail/send"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                # SendGrid returns 202 on success.
                if resp.status_code in (200, 201, 202):
                    return True
                logger.error(
                    "SendGrid API returned %d for %s: %s",
                    resp.status_code, to_addr, resp.text,
                )
                return False
        except Exception:
            logger.exception("SendGrid send failed for %s", to_addr)
            return False

    async def test_connection(self) -> bool:
        import httpx

        url = f"{self.base_url}/v3/scopes"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            logger.exception("SendGrid connection test failed")
            return False


# ---------------------------------------------------------------------------
# Benchmark (no-op sink for load testing / performance benchmarking)
# ---------------------------------------------------------------------------

class BenchmarkBackend(SmtpBackend):
    """No-op mail backend for load testing and performance benchmarking.

    Simulates sending without touching any external service.  Optionally
    introduces artificial latency and a configurable failure rate so that
    realistic throughput / error-handling behaviour can be measured.

    Metrics are kept in-process via a bounded deque and atomic counters.
    When ``metrics_redis_key`` is set, aggregate metrics are pushed to
    Redis every 1000 sends for external consumption.
    """

    _METRICS_FLUSH_INTERVAL = 1000
    _DEQUE_MAXLEN = 10_000

    def __init__(
        self,
        simulated_latency_ms: float = 0.0,
        failure_rate: float = 0.0,
        metrics_redis_key: str | None = None,
    ) -> None:
        self.simulated_latency_ms = simulated_latency_ms
        self.failure_rate = max(0.0, min(1.0, failure_rate))
        self.metrics_redis_key = metrics_redis_key

        # Bounded ring buffer for per-send timing data.
        self._timings: deque[tuple[float, float, bool]] = deque(
            maxlen=self._DEQUE_MAXLEN,
        )

        # Atomic counters protected by a lock.
        self._lock = threading.Lock()
        self._total_sent: int = 0
        self._total_failed: int = 0
        self._total_bytes: int = 0
        self._start_time: float = time.monotonic()

    # -- SmtpBackend interface -----------------------------------------------

    async def send(
        self,
        from_addr: str,
        from_name: str | None,
        to_addr: str,
        subject: str,
        body_html: str,
        body_text: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        t0 = time.monotonic()

        # Simulate network latency.
        if self.simulated_latency_ms > 0:
            await asyncio.sleep(self.simulated_latency_ms / 1000.0)

        # Simulate transient failures.
        success = True
        if self.failure_rate > 0 and random.random() < self.failure_rate:
            success = False

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        message_bytes = len((body_html or "").encode()) + len((body_text or "").encode())

        # Record timing entry.
        self._timings.append((time.time(), elapsed_ms, success))

        # Update atomic counters.
        with self._lock:
            if success:
                self._total_sent += 1
            else:
                self._total_failed += 1
            self._total_bytes += message_bytes

            total_ops = self._total_sent + self._total_failed

        # Periodic flush to Redis.
        if (
            self.metrics_redis_key
            and total_ops > 0
            and total_ops % self._METRICS_FLUSH_INTERVAL == 0
        ):
            self._flush_metrics_to_redis()

        return success

    async def test_connection(self) -> bool:
        return True

    # -- Metrics -------------------------------------------------------------

    def get_metrics_summary(self) -> dict[str, Any]:
        """Return a snapshot of accumulated benchmark metrics."""
        with self._lock:
            total_sent = self._total_sent
            total_failed = self._total_failed
            total_bytes = self._total_bytes

        elapsed_sec = max(0.001, time.monotonic() - self._start_time)

        # Compute latency percentiles from the deque snapshot.
        latencies = [entry[1] for entry in self._timings]
        latencies.sort()

        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        p95 = self._percentile(latencies, 0.95)
        p99 = self._percentile(latencies, 0.99)

        return {
            "total_sent": total_sent,
            "total_failed": total_failed,
            "total_bytes": total_bytes,
            "avg_latency_ms": round(avg_latency, 3),
            "p95_latency_ms": round(p95, 3),
            "p99_latency_ms": round(p99, 3),
            "throughput_per_sec": round(
                (total_sent + total_failed) / elapsed_sec, 2,
            ),
        }

    @staticmethod
    def _percentile(sorted_values: list[float], pct: float) -> float:
        """Compute a percentile from a pre-sorted list."""
        if not sorted_values:
            return 0.0
        idx = int(len(sorted_values) * pct)
        idx = min(idx, len(sorted_values) - 1)
        return sorted_values[idx]

    def _flush_metrics_to_redis(self) -> None:
        """Push aggregate metrics to Redis (best-effort, non-blocking)."""
        try:
            import redis as _redis
            from app.config import settings

            r = _redis.from_url(settings.REDIS_URL)
            summary = self.get_metrics_summary()
            r.hset(self.metrics_redis_key, mapping={
                k: str(v) for k, v in summary.items()
            })
            r.expire(self.metrics_redis_key, 86400)
        except Exception:
            logger.debug(
                "Failed to flush benchmark metrics to Redis key %s",
                self.metrics_redis_key,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_backend(smtp_profile) -> SmtpBackend:
    """Instantiate the correct SmtpBackend subclass based on the profile's
    ``backend_type``.

    Parameters
    ----------
    smtp_profile:
        An ``SmtpProfile`` ORM object.

    Returns
    -------
    SmtpBackend
        A configured backend instance ready to send.

    Raises
    ------
    ValueError
        If the ``backend_type`` is not recognised.
    """
    from app.models.smtp_profile import BackendType

    bt = smtp_profile.backend_type
    config: dict[str, Any] = smtp_profile.config or {}

    if bt == BackendType.SMTP:
        return SmtpRelayBackend(
            host=smtp_profile.host or "localhost",
            port=smtp_profile.port or 587,
            username=smtp_profile.username,
            password=smtp_profile.password,
            use_tls=smtp_profile.use_tls,
            use_ssl=smtp_profile.use_ssl,
        )

    if bt == BackendType.SES:
        return SesBackend(
            region=config.get("region", "us-east-1"),
            aws_access_key_id=config.get("aws_access_key_id"),
            aws_secret_access_key=config.get("aws_secret_access_key"),
        )

    if bt == BackendType.MAILGUN:
        return MailgunBackend(
            api_key=config.get("api_key", ""),
            domain=config.get("domain", ""),
            base_url=config.get("base_url", "https://api.mailgun.net/v3"),
        )

    if bt == BackendType.SENDGRID:
        return SendGridBackend(
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url", "https://api.sendgrid.com"),
        )

    if bt == BackendType.BENCHMARK:
        return BenchmarkBackend(
            simulated_latency_ms=config.get("simulated_latency_ms", 0.0),
            failure_rate=config.get("failure_rate", 0.0),
            metrics_redis_key=config.get("metrics_redis_key"),
        )

    raise ValueError(f"Unknown backend type: {bt!r}")

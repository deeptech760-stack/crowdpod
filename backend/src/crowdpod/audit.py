"""Who used the site, what looked malicious, and telling the owner about it.

Every sign-in and every guardrail that fires is written to the `audit` table with the account,
address and time. Serious events (and bursts of smaller ones from the same account or address)
are emailed to the administrators, who can block the account from the admin console. Nothing is
blocked automatically: the owner decides.

Events never contain passwords, tokens or API keys, and are deleted after `RETENTION_DAYS`.
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
import threading
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

from .store import Store

log = logging.getLogger("crowdpod.security")

RETENTION_DAYS = 90
BURST = 5  # this many warnings from one account or address within an hour sends an alert
ALERT_EVERY = 30 * 60  # at most one email per account/address and kind of event per 30 minutes

SCHEMA = """
create table if not exists audit (
  id integer primary key autoincrement, at real not null, user_id text, email text, ip text,
  kind text not null, severity text not null, detail text not null
);
create index if not exists audit_user on audit (user_id, at);
create index if not exists audit_ip on audit (ip, at);
"""

# what each kind of event means, for the console and the alert emails
KINDS = {
    "register": "Created an account",
    "login": "Signed in",
    "login_failed": "Wrong password",
    "lockout": "Locked out after repeated wrong passwords",
    "signup_limit": "Too many sign-ups from one address",
    "blocked_access": "A blocked account tried to use the site",
    "bad_token": "Used an invalid or revoked access token",
    "cross_site": "Cross-site request (possible CSRF)",
    "oversize": "Sent an oversized request",
    "ssrf": "Pointed the browsers at a private or internal address",
    "browser_blocked": "A visited page tried to reach a private or internal address",
    "quota": "Hit a usage limit",
    "injection": "Idea text looks like a prompt-injection attempt",
    "admin_denied": "Tried to use an administrator feature",
    "token_created": "Created an access token",
    "token_revoked": "Revoked an access token",
    "blocked": "Account blocked by an administrator",
    "unblocked": "Account unblocked by an administrator",
}

INJECTION = re.compile(
    r"ignore (all |the )?(previous|prior|above) (instructions|prompts?)|disregard (your|the) (instructions|rules)"
    r"|system prompt|you are now|developer mode|jailbreak|reveal (your|the) (prompt|instructions|api key)"
    r"|print (your|the) (prompt|instructions|env)|<\s*/?\s*(system|assistant)\s*>",
    re.IGNORECASE,
)


def looks_like_injection(*texts: str) -> str:
    """The first suspicious phrase in the text, or '' (flagged for review, never acted on)."""
    for text in texts:
        m = INJECTION.search(text or "")
        if m:
            return m.group(0)
    return ""


@dataclass(frozen=True)
class MailSettings:
    host: str = field(default_factory=lambda: os.environ.get("CROWDPOD_SMTP_HOST", ""))
    port: int = field(default_factory=lambda: int(os.environ.get("CROWDPOD_SMTP_PORT", "587")))
    user: str = field(default_factory=lambda: os.environ.get("CROWDPOD_SMTP_USER", ""))
    password: str = field(default_factory=lambda: os.environ.get("CROWDPOD_SMTP_PASSWORD", ""))
    sender: str = field(default_factory=lambda: os.environ.get("CROWDPOD_SMTP_FROM", ""))

    @property
    def configured(self) -> bool:
        return bool(self.host and (self.sender or self.user))


class Mailer:
    """Sends alert emails over SMTP on a background thread, so a slow mail server never slows a request."""

    def __init__(self, settings: MailSettings | None = None):
        self.settings = settings or MailSettings()
        self.sent: list[EmailMessage] = []  # kept for tests and the console's "last alert" line

    def send(self, to: tuple[str, ...], subject: str, body: str) -> bool:
        if not to or not self.settings.configured:
            log.warning("alert (email not configured): %s", subject)
            return False
        msg = EmailMessage()
        msg["From"] = self.settings.sender or self.settings.user
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.set_content(body)
        self.sent.append(msg)
        threading.Thread(target=self._deliver, args=(msg,), daemon=True).start()
        return True

    def _deliver(self, msg: EmailMessage) -> None:
        s = self.settings
        try:
            if s.port == 465:
                server: smtplib.SMTP = smtplib.SMTP_SSL(s.host, s.port, timeout=20)
            else:
                server = smtplib.SMTP(s.host, s.port, timeout=20)
                server.starttls()
            with server:
                if s.user:
                    server.login(s.user, s.password)
                server.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            log.error("could not send alert email: %s", type(e).__name__)


class Audit:
    def __init__(self, store: Store, *, admins: tuple[str, ...], app_url: str, alert_to: tuple[str, ...] = (),
                 mailer: Mailer | None = None):
        self.store = store
        self.admins = admins
        self.alert_to = alert_to or admins
        self.app_url = app_url
        self.mailer = mailer or Mailer()
        self._alerted: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()
        with store._lock:
            store._db.executescript(SCHEMA)
            store._db.execute("delete from audit where at < ?", (time.time() - RETENTION_DAYS * 86400,))
            store._db.commit()

    def record(self, kind: str, *, severity: str = "info", user: Any = None, email: str = "", ip: str = "",
               detail: str = "") -> None:
        user_id = getattr(user, "id", None) or None
        email = (getattr(user, "email", "") or email or "")[:200]
        detail = detail.replace("\n", " ")[:500]
        self.store._exec(
            "insert into audit (at, user_id, email, ip, kind, severity, detail) values (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), user_id, email, ip[:64], kind, severity, detail),
        )
        if severity != "info":
            log.warning("%s %s user=%s ip=%s %s", severity, kind, user_id or email or "-", ip or "-", detail)
        self._maybe_alert(kind, severity, user_id, email, ip, detail)

    def _maybe_alert(self, kind: str, severity: str, user_id: str | None, email: str, ip: str, detail: str) -> None:
        if severity == "info":
            return
        who = user_id or ip or email
        if severity != "high":
            column, value = ("user_id", user_id) if user_id else ("ip", ip)
            if not value:
                return
            recent = self.store._all(
                f"select count(*) as n from audit where {column} = ? and severity != 'info' and at > ?",
                (value, time.time() - 3600),
            )[0]["n"]
            if recent < BURST:
                return
            kind = "burst"
        with self._lock:
            key = (who, kind)
            if time.time() - self._alerted.get(key, 0) < ALERT_EVERY:
                return
            self._alerted[key] = time.time()
        what = KINDS.get(kind, f"{BURST} or more warnings within an hour")
        subject = f"[Crowdpod] {what}: {email or ip or 'unknown'}"
        body = (
            f"{what}.\n\nAccount: {email or '(not signed in)'}\nAddress: {ip or 'unknown'}\n"
            f"When: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\nDetail: {detail or '-'}\n\n"
            f"Review the account and block it if needed:\n{self.app_url}/app/admin/\n"
        )
        self.mailer.send(self.alert_to, subject, body)

    # ------------------------------------------------------------ console queries
    def events(self, *, user_id: str | None = None, severity: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        where, args = [], []
        if user_id:
            where.append("user_id = ?")
            args.append(user_id)
        if severity == "alerts":
            where.append("severity != 'info'")
        clause = ("where " + " and ".join(where)) if where else ""
        rows = self.store._all(f"select * from audit {clause} order by id desc limit ?", (*args, max(1, min(limit, 1000))))
        return [{**dict(r), "label": KINDS.get(r["kind"], r["kind"])} for r in rows]

    def users(self) -> list[dict[str, Any]]:
        week = time.time() - 7 * 86400
        rows = self.store._all(
            """
            select u.id, u.email, u.name, u.google_sub is not null as google, u.created_at, u.blocked, u.blocked_reason,
                   (select max(at) from audit a where a.user_id = u.id) as last_login,
                   (select ip from audit a where a.user_id = u.id and a.kind in ('login', 'register') order by id desc limit 1) as last_ip,
                   (select count(*) from runs r where r.owner = u.id) as runs,
                   (select count(*) from audit a where a.user_id = u.id and a.severity != 'info' and a.at > ?) as warnings
            from users u order by coalesce(last_login, u.created_at) desc
            """,
            (week,),
        )
        return [{**dict(r), "google": bool(r["google"]), "blocked": bool(r["blocked"]),
                 "admin": r["email"] in self.admins} for r in rows]

    def stats(self) -> dict[str, int]:
        day = time.time() - 86400
        one = lambda sql, *a: self.store._all(sql, a)[0][0]  # noqa: E731
        return {
            "users": one("select count(*) from users"),
            "signed_in_24h": one("select count(distinct user_id) from audit where kind in ('login', 'register') and at > ?", day),
            "runs_24h": one("select count(*) from runs where created_at > ?", day),
            "warnings_24h": one("select count(*) from audit where severity != 'info' and at > ?", day),
            "blocked": one("select count(*) from users where blocked = 1"),
        }

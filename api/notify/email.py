"""Email delivery of the daily brief via stdlib smtplib."""
import logging
import re
import smtplib
from email.message import EmailMessage
from config import settings

log = logging.getLogger("recon.notify.email")


def _markdown_to_html(markdown: str) -> str:
    """Minimal markdown-to-HTML conversion — enough for the brief's
    headings, bold, list items, and paragraphs."""
    lines = markdown.splitlines()
    html_lines: list[str] = []
    in_list = False

    def inline(text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        return text

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{inline(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{inline(stripped[3:])}</h2>")
        elif stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{inline(stripped[2:])}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{inline(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")

    return (
        "<html><body style=\"font-family: sans-serif; max-width: 720px;\">"
        + "\n".join(html_lines)
        + "</body></html>"
    )


def send_email(subject: str, markdown_body: str) -> None:
    """Send the daily brief by email (plain text + minimal HTML).

    No-ops (with a warning) if email delivery is disabled or SMTP is
    not fully configured.
    """
    if not settings.notify_email_enabled:
        log.warning("email: notify_email_enabled is False — skipping")
        return
    if not (settings.smtp_host and settings.email_from and settings.email_to):
        log.warning("email: SMTP not configured (host/from/to) — skipping")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = settings.email_to
    msg.set_content(markdown_body)
    msg.add_alternative(_markdown_to_html(markdown_body), subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    log.info("email: sent brief to %s", settings.email_to)

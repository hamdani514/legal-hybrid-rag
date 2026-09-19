import asyncio
from datetime import datetime
import html
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from loguru import logger

from app.config import settings


def is_real_smtp_configured() -> bool:
    user = (settings.SMTP_USER or "").strip()
    password = (settings.SMTP_PASS or "").strip()
    return (
        bool(user)
        and "your_email" not in user
        and bool(password)
        and "your_16_char" not in password
    )


def _log_simulated_email(to_email: str, subject: str, body: str) -> None:
    # Clean basic HTML tags for terminal preview
    preview = re.sub(r"<style[\s\S]*?</style>", "", body, flags=re.IGNORECASE)
    preview = re.sub(r"<script[\s\S]*?</script>", "", preview, flags=re.IGNORECASE)
    preview = re.sub(r"</div\s*>", "\n", preview, flags=re.IGNORECASE)
    preview = re.sub(r"</p\s*>", "\n", preview, flags=re.IGNORECASE)
    preview = re.sub(r"<br\s*/?>", "\n", preview, flags=re.IGNORECASE)
    preview = re.sub(r"<[^>]+>", "", preview)
    preview = html.unescape(preview)
    preview = re.sub(r"\n\s*\n\s*\n", "\n\n", preview).strip()

    bar = "=" * 70
    logger.info(
        f"\n{bar}\n"
        f"📬 [DEV EMAIL SIMULATION - No real email sent]\n"
        f"👤 To:      {to_email}\n"
        f"📋 Subject: {subject}\n"
        f"{'-' * 70}\n"
        f"{preview}\n"
        f"{bar}\n"
    )


def _send_sync_smtp(to_email: str, subject: str, html_body: str, reply_to: str = None) -> bool:
    msg = MIMEMultipart("alternative")
    sender_user = settings.SMTP_USER.strip()
    msg["From"] = f'"Legal RAG Support" <{sender_user}>'
    msg["To"] = to_email
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to

    # Plaintext fallback from HTML
    plain_text = re.sub(r"<[^>]+>", "", html_body)
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    port = int(settings.SMTP_PORT or 587)
    host = settings.SMTP_HOST or "smtp.gmail.com"
    password = settings.SMTP_PASS.strip()

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            server.login(sender_user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_user, password)
            server.send_message(msg)
    return True


async def send_mail(to_email: str, subject: str, html_body: str, reply_to: str = None) -> bool:
    if is_real_smtp_configured():
        try:
            await asyncio.to_thread(_send_sync_smtp, to_email, subject, html_body, reply_to)
            logger.info(f"✅ [SMTP] Real email successfully sent to {to_email}: '{subject}'")
            return True
        except Exception as e:
            logger.warning(f"⚠️ [SMTP] Real SMTP delivery failed ({e}). Falling back to simulation preview.")
            _log_simulated_email(to_email, subject, html_body)
            return False
    else:
        _log_simulated_email(to_email, subject, html_body)
        return True


# -------------------------------------------------------------
# Specific Templates matching RagModules-main
# -------------------------------------------------------------

# -------------------------------------------------------------
# Specific Templates matching User Requirements
# -------------------------------------------------------------

def _email_container(title: str, subtitle: str, content_html: str, footer_note: str = "") -> str:
    year = datetime.now().year
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>{title}</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: #1e293b;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f1f5f9; padding: 32px 16px;">
        <tr>
          <td align="center">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.08);">
              
              <!-- Brand Header -->
              <tr>
                <td style="background: linear-gradient(135deg, #0D1C32 0%, #172D4D 100%); padding: 32px 28px; text-align: center; border-bottom: 3px solid #C5A880;">
                  <div style="display: inline-block; padding: 6px 16px; background-color: rgba(197, 168, 128, 0.15); border: 1px solid rgba(197, 168, 128, 0.4); border-radius: 20px; margin-bottom: 8px;">
                    <span style="font-size: 11px; font-weight: 700; color: #E9C176; text-transform: uppercase; letter-spacing: 1.5px;">Verdict AI • Legal Hybrid RAG</span>
                  </div>
                  <h1 style="color: #ffffff; font-size: 22px; font-weight: 700; margin: 6px 0 2px 0; letter-spacing: -0.02em;">{title}</h1>
                  <p style="color: #94a3b8; font-size: 13px; margin: 0;">{subtitle}</p>
                </td>
              </tr>

              <!-- Main Content Body -->
              <tr>
                <td style="padding: 32px 28px; background-color: #ffffff;">
                  {content_html}
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="padding: 24px 28px; background-color: #f8fafc; border-top: 1px solid #f1f5f9; text-align: center;">
                  {f'<p style="color: #64748b; font-size: 12px; line-height: 1.5; margin: 0 0 12px 0;">{footer_note}</p>' if footer_note else ''}
                  <p style="color: #94a3b8; font-size: 12px; margin: 0; line-height: 1.5;">
                    © {year} Verdict AI • Supreme Court Intelligence System.<br />
                    All rights reserved. Secure legal communications.
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


async def send_otp_email(user_name: str, user_email: str, otp: str) -> bool:
    safe_name = html.escape(user_name or "Counselor")
    subject = "Your 6-Digit Password Reset OTP"

    content_html = f"""
        <p style="color: #334155; font-size: 15px; line-height: 1.6; margin-top: 0;">
            Hi <strong>{safe_name}</strong>,
        </p>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            We received a request to reset the password for your Legal Hybrid RAG account. Use the 6-digit authorization code below to proceed:
        </p>

        <!-- 6-Digit OTP Box -->
        <div style="text-align: center; margin: 28px 0;">
            <div style="display: inline-block; background-color: #0D1C32; color: #ffffff; font-size: 36px; font-weight: 800; letter-spacing: 12px; padding: 18px 36px; border-radius: 12px; border: 2px solid #C5A880; box-shadow: 0 4px 12px rgba(13, 28, 50, 0.25);">
                {otp}
            </div>
        </div>

        <!-- 1-Minute Expiry Warning Banner -->
        <div style="background-color: #FEF2F2; border-left: 4px solid #EF4444; border-radius: 8px; padding: 14px 18px; margin: 24px 0;">
            <div style="font-size: 13px; font-weight: 700; color: #991B1B; margin-bottom: 2px; display: flex; align-items: center;">
                ⏱️ Security Notice: 1-Minute Expiration
            </div>
            <p style="margin: 0; font-size: 13px; color: #B91C1C; line-height: 1.5;">
                This code expires in exactly <strong>60 seconds (1 minute)</strong>. Please enter it immediately on the verification screen.
            </p>
        </div>

        <p style="color: #64748b; font-size: 13px; line-height: 1.5; margin-bottom: 0;">
            If you did not request this password recovery, you can safely disregard this email. Your password will remain unchanged.
        </p>
    """

    html_body = _email_container(
        title="Password Reset Authorization",
        subtitle="One-Time Verification Code",
        content_html=content_html,
        footer_note="Never share your verification code with anyone. Our support team will never ask for your OTP."
    )
    return await send_mail(user_email, subject, html_body)


async def send_password_changed_email(user_name: str, user_email: str) -> bool:
    safe_name = html.escape(user_name or "Counselor")
    subject = "Security Notice: Your Password Has Been Updated"
    timestamp_str = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")

    content_html = f"""
        <div style="text-align: center; margin-bottom: 24px;">
            <div style="display: inline-block; width: 56px; height: 56px; line-height: 56px; border-radius: 50%; background-color: #ECFDF5; color: #059669; font-size: 28px; margin-bottom: 12px;">
                ✓
            </div>
            <h2 style="color: #059669; font-size: 20px; font-weight: 700; margin: 0;">Password Successfully Reset</h2>
        </div>

        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            Hi <strong>{safe_name}</strong>,
        </p>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            Your account password was successfully changed on <strong>{timestamp_str}</strong>. You can now use your new credentials to access the legal portal.
        </p>

        <div style="text-align: center; margin: 28px 0;">
            <a href="{settings.FRONTEND_URL}/login" style="background-color: #0D1C32; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 700; font-size: 14px; display: inline-block;">
                Sign In to Legal Portal
            </a>
        </div>

        <div style="background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 12px 16px; margin-top: 24px;">
            <p style="margin: 0; font-size: 12px; color: #991B1B; line-height: 1.5;">
                ⚠️ <strong>Didn't make this change?</strong> If you did not update your password, please reach out to our emergency support immediately at <strong>verdictaisupport@gmail.com</strong>.
            </p>
        </div>
    """

    html_body = _email_container(
        title="Account Security Alert",
        subtitle="Credentials Modification Confirmation",
        content_html=content_html
    )
    return await send_mail(user_email, subject, html_body)


async def send_deactivation_email(user_name: str, user_email: str, reactivate_url: str, days: int = 30) -> bool:
    safe_name = html.escape(user_name or "Counselor")
    subject = "Account Deactivation & Reactivation Link"

    content_html = f"""
        <p style="color: #334155; font-size: 15px; line-height: 1.6; margin-top: 0;">
            Hi <strong>{safe_name}</strong>,
        </p>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            As requested, your Legal Hybrid RAG account has been deactivated. All active sessions have been terminated.
        </p>

        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 20px; margin: 24px 0;">
            <h3 style="color: #0D1C32; font-size: 16px; margin: 0 0 8px 0; font-weight: 700;">
                How to Reactivate Your Account:
            </h3>
            <p style="color: #475569; font-size: 14px; line-height: 1.5; margin: 0 0 16px 0;">
                You can easily restore your account and all saved research data within the next <strong>{days} days</strong> by clicking the secure reactivation button below:
            </p>

            <div style="text-align: center; margin: 20px 0 12px 0;">
                <a href="{reactivate_url}" style="background-color: #0D1C32; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 700; font-size: 15px; display: inline-block; border: 1px solid #C5A880; box-shadow: 0 4px 10px rgba(13, 28, 50, 0.2);">
                    Reactivate My Account & Sign In →
                </a>
            </div>
            <p style="color: #64748b; font-size: 12px; text-align: center; margin: 0;">
                Clicking will restore your active status and take you directly to Sign In.
            </p>
        </div>

        <p style="color: #64748b; font-size: 13px; line-height: 1.5;">
            Or copy and paste this link into your web browser:<br />
            <a href="{reactivate_url}" style="color: #2563eb; word-break: break-all; font-size: 12px;">{reactivate_url}</a>
        </p>

        <p style="color: #94a3b8; font-size: 12px; line-height: 1.5; margin-bottom: 0;">
            Note: This reactivation link is valid for {days} days. After this period, permanent archival may apply.
        </p>
    """

    html_body = _email_container(
        title="Account Status Update",
        subtitle="Deactivation Notice & Recovery Key",
        content_html=content_html
    )
    return await send_mail(user_email, subject, html_body)


async def send_reactivation_link_email(user_name: str, user_email: str, reactivate_url: str, days: int = 30) -> bool:
    safe_name = html.escape(user_name or "Counselor")
    subject = "Your Account Reactivation Link - Legal Hybrid RAG"

    content_html = f"""
        <p style="color: #334155; font-size: 15px; line-height: 1.6; margin-top: 0;">
            Hi <strong>{safe_name}</strong>,
        </p>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            We received a request to reactivate your Legal Hybrid RAG account (<strong>{user_email}</strong>).
        </p>

        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 20px; margin: 24px 0;">
            <h3 style="color: #0D1C32; font-size: 16px; margin: 0 0 8px 0; font-weight: 700;">
                Restore Account Access:
            </h3>
            <p style="color: #475569; font-size: 14px; line-height: 1.5; margin: 0 0 16px 0;">
                Click the secure button below to restore your account to Active status and proceed directly to Sign In:
            </p>

            <div style="text-align: center; margin: 20px 0 12px 0;">
                <a href="{reactivate_url}" style="background-color: #0D1C32; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 700; font-size: 15px; display: inline-block; border: 1px solid #C5A880; box-shadow: 0 4px 10px rgba(13, 28, 50, 0.2);">
                    Reactivate My Account & Sign In →
                </a>
            </div>
            <p style="color: #64748b; font-size: 12px; text-align: center; margin: 0;">
                This link will remain valid for {days} days.
            </p>
        </div>

        <p style="color: #64748b; font-size: 13px; line-height: 1.5;">
            Or copy and paste this link into your web browser:<br />
            <a href="{reactivate_url}" style="color: #2563eb; word-break: break-all; font-size: 12px;">{reactivate_url}</a>
        </p>

        <p style="color: #94a3b8; font-size: 12px; line-height: 1.5; margin-bottom: 0;">
            If you did not initiate this request, you can safely disregard this email. Your account will remain deactivated until you choose to restore it.
        </p>
    """

    html_body = _email_container(
        title="Account Reactivation Link",
        subtitle="Access Recovery Portal",
        content_html=content_html,
        footer_note="Secure account reactivation link requested from the login portal."
    )
    return await send_mail(user_email, subject, html_body)


async def send_reactivation_confirmation_email(user_name: str, user_email: str) -> bool:
    safe_name = html.escape(user_name or "Counselor")
    subject = "Welcome Back! Your Account Has Been Reactivated"
    timestamp_str = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")

    content_html = f"""
        <div style="text-align: center; margin-bottom: 24px;">
            <div style="display: inline-block; width: 56px; height: 56px; line-height: 56px; border-radius: 50%; background-color: #ECFDF5; color: #059669; font-size: 28px; margin-bottom: 12px;">
                ✓
            </div>
            <h2 style="color: #059669; font-size: 20px; font-weight: 700; margin: 0;">Account Successfully Reactivated</h2>
        </div>

        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            Hi <strong>{safe_name}</strong>,
        </p>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            Your account was successfully restored on <strong>{timestamp_str}</strong>. Your subscription features and saved legal research cases are ready for you.
        </p>

        <div style="text-align: center; margin: 28px 0;">
            <a href="{settings.FRONTEND_URL}/login" style="background-color: #0D1C32; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 700; font-size: 15px; display: inline-block; border: 1px solid #C5A880;">
                Sign In to Legal Portal
            </a>
        </div>
    """

    html_body = _email_container(
        title="Account Reactivation Complete",
        subtitle="Access Restored",
        content_html=content_html
    )
    return await send_mail(user_email, subject, html_body)


# -------------------------------------------------------------
# Contact Query Email Templates
# -------------------------------------------------------------

async def send_contact_notification(name: str, email: str, subject: str, message: str, query_id: str) -> bool:
    admin_recipient = (settings.CONTACT_RECEIVER_EMAIL or "verdictaisupport@gmail.com").strip()
    safe_name = html.escape(name or "Unknown")
    safe_email = html.escape(email or "")
    safe_subject = html.escape(subject or "No Subject")
    safe_message = html.escape(message or "").replace("\n", "<br/>")
    timestamp_str = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")

    mail_subject = f"[Inquiry #{query_id}] {subject}"
    content_html = f"""
        <div style="margin-bottom: 20px;">
            <span style="display: inline-block; padding: 4px 12px; background-color: #0D1C32; color: #E9C176; font-weight: 700; border-radius: 6px; font-size: 12px; letter-spacing: 1px;">
                TICKET REF: {query_id}
            </span>
        </div>

        <h3 style="color: #0D1C32; font-size: 18px; margin: 0 0 16px 0; font-weight: 700;">
            New Contact Form Inquiry Submitted
        </h3>

        <table style="width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 24px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
            <tr style="background-color: #f8fafc;">
                <td style="padding: 12px 16px; font-weight: 700; width: 130px; color: #475569; border-bottom: 1px solid #e2e8f0;">Client Name</td>
                <td style="padding: 12px 16px; color: #0f172a; font-weight: 600; border-bottom: 1px solid #e2e8f0;">{safe_name}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; font-weight: 700; color: #475569; border-bottom: 1px solid #e2e8f0; background-color: #f8fafc;">Client Email</td>
                <td style="padding: 12px 16px; color: #0f172a; border-bottom: 1px solid #e2e8f0;">
                    <a href="mailto:{safe_email}" style="color: #2563eb; text-decoration: none; font-weight: 600;">{safe_email}</a>
                </td>
            </tr>
            <tr style="background-color: #f8fafc;">
                <td style="padding: 12px 16px; font-weight: 700; color: #475569; border-bottom: 1px solid #e2e8f0;">Subject</td>
                <td style="padding: 12px 16px; color: #0f172a; font-weight: 600; border-bottom: 1px solid #e2e8f0;">{safe_subject}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; font-weight: 700; vertical-align: top; color: #475569; border-bottom: 1px solid #e2e8f0; background-color: #f8fafc;">Message</td>
                <td style="padding: 12px 16px; color: #1e293b; line-height: 1.6; border-bottom: 1px solid #e2e8f0; background-color: #ffffff;">
                    {safe_message}
                </td>
            </tr>
            <tr style="background-color: #f8fafc;">
                <td style="padding: 12px 16px; font-weight: 700; color: #475569;">Submitted At</td>
                <td style="padding: 12px 16px; color: #64748b; font-size: 13px;">{timestamp_str}</td>
            </tr>
        </table>

        <div style="background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 12px 16px;">
            <p style="color: #1E40AF; font-size: 13px; margin: 0; line-height: 1.5;">
                💡 <strong>Direct Reply Ready:</strong> The Reply-To header is set to <strong>{safe_email}</strong>. Simply click "Reply" in your email client to respond to the user.
            </p>
        </div>
    """

    html_body = _email_container(
        title="Support Desk Dispatch",
        subtitle=f"Incoming Inquiry [{query_id}]",
        content_html=content_html
    )
    return await send_mail(admin_recipient, mail_subject, html_body, reply_to=email)


async def send_contact_acknowledgement(name: str, email: str, subject: str, query_id: str) -> bool:
    safe_name = html.escape(name or "Counselor")
    safe_subject = html.escape(subject or "Your Inquiry")
    mail_subject = f"We have received your query [Ticket #{query_id}] - Legal Hybrid RAG Support"

    content_html = f"""
        <div style="margin-bottom: 20px;">
            <span style="display: inline-block; padding: 5px 14px; background-color: #ECFDF5; color: #059669; font-weight: 700; border-radius: 20px; font-size: 12px; border: 1px solid #A7F3D0;">
                ✓ Inquiry Received • Reference ID: {query_id}
            </span>
        </div>

        <h2 style="color: #0D1C32; font-size: 20px; font-weight: 700; margin: 0 0 16px 0;">
            Thank you for contacting us, {safe_name}.
        </h2>

        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            We have successfully received your inquiry regarding <strong>"{safe_subject}"</strong>.
        </p>

        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
            Our legal operations and engineering team is actively reviewing your message. We will analyze your query and follow up with a detailed response <strong>within 24 to 48 hours</strong>.
        </p>

        <!-- Reference Box -->
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #0D1C32; border-radius: 8px; padding: 16px 20px; margin: 24px 0;">
            <div style="font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">
                Inquiry Summary:
            </div>
            <table style="width: 100%; font-size: 13px; color: #334155; border-collapse: collapse;">
                <tr>
                    <td style="padding: 4px 0; width: 140px; color: #64748b;">Ticket Reference:</td>
                    <td style="padding: 4px 0; font-weight: 700; color: #0D1C32;">{query_id}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #64748b;">Expected Response:</td>
                    <td style="padding: 4px 0; font-weight: 700; color: #059669;">Within 24 to 48 Hours</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #64748b;">Support Channel:</td>
                    <td style="padding: 4px 0; font-weight: 600;">verdictaisupport@gmail.com</td>
                </tr>
            </table>
        </div>

        <p style="color: #64748b; font-size: 13px; line-height: 1.5; margin-bottom: 0;">
            If you need to provide additional details, files, or citations, you can simply reply directly to this email thread.
        </p>
    """

    html_body = _email_container(
        title="Inquiry Acknowledged",
        subtitle="Supreme Court Research Assistance",
        content_html=content_html,
        footer_note="This email confirms your inquiry has been logged into our support queue."
    )
    return await send_mail(email, mail_subject, html_body)

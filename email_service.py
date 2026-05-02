import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587


def _build_html(student):
    name       = student.get('name',       'Student')
    mobile     = student.get('mobile',     '—')
    batch_name = student.get('batch_name', '—')

    return f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#f0f4f8;padding:40px 16px;">
    <tr><td align="center">

      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:10px;
                    box-shadow:0 4px 16px rgba(0,0,0,0.08);
                    overflow:hidden;max-width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:#3b82f6;padding:28px 32px;text-align:center;">
            <h1 style="color:#ffffff;margin:0;font-size:22px;font-weight:700;
                       letter-spacing:0.01em;">
              &#10003;&nbsp; Registration Confirmed!
            </h1>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px 36px;">

            <p style="font-size:16px;color:#1a202c;margin:0 0 12px;font-weight:600;">
              Hi {name},
            </p>
            <p style="font-size:15px;color:#4a5568;line-height:1.7;margin:0 0 28px;">
              You have successfully registered for the
              <strong style="color:#1a202c;">Python Programming</strong> class.
              We&rsquo;re glad to have you on board!
            </p>

            <!-- Details -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f8fafc;border-radius:8px;
                          border:1px solid #e2e8f0;margin-bottom:28px;">
              <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px 16px;font-size:13px;
                           color:#718096;font-weight:600;width:35%;">Name</td>
                <td style="padding:10px 16px;font-size:13px;
                           color:#1a202c;font-weight:700;">{name}</td>
              </tr>
              <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px 16px;font-size:13px;color:#718096;font-weight:600;">Mobile</td>
                <td style="padding:10px 16px;font-size:13px;color:#1a202c;font-weight:700;">{mobile}</td>
              </tr>
              <tr>
                <td style="padding:10px 16px;font-size:13px;color:#718096;font-weight:600;">Batch</td>
                <td style="padding:10px 16px;font-size:13px;color:#1a202c;font-weight:700;">{batch_name}</td>
              </tr>
            </table>

            <p style="font-size:15px;color:#4a5568;margin:0 0 4px;">
              See you in class!
            </p>
            <p style="font-size:15px;color:#1a202c;font-weight:700;margin:0;">
              &ndash; Besant Technologies
            </p>

          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:14px 36px;
                     border-top:1px solid #e2e8f0;text-align:center;">
            <p style="font-size:12px;color:#a0aec0;margin:0;">
              This is an automated message. Please do not reply to this email.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_registration_email(student):
    """
    Send an HTML confirmation email to the newly registered student.
    Reads GMAIL_USER and GMAIL_PASSWORD from environment variables.
    Logs errors silently — never raises so the app keeps running.
    """
    gmail_user     = os.environ.get('GMAIL_USER')
    gmail_password = os.environ.get('GMAIL_PASSWORD')

    if not gmail_user or not gmail_password:
        logger.warning('GMAIL_USER or GMAIL_PASSWORD not configured — email skipped.')
        return

    to_addr = student.get('email')
    if not to_addr:
        logger.warning('Student has no email address — email skipped.')
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Welcome to Python Programming Class – Registration Confirmed!'
    msg['From']    = gmail_user
    msg['To']      = to_addr
    msg.attach(MIMEText(_build_html(student), 'html', 'utf-8'))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(gmail_user, gmail_password)
            smtp.sendmail(gmail_user, to_addr, msg.as_string())
        logger.info('Confirmation email sent to %s', to_addr)
    except Exception as exc:
        logger.error('Failed to send confirmation email to %s: %s', to_addr, exc)

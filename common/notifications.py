# agfaEiServerUtils\common\notifications.py

import logging
import smtplib
import html
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(smtp_recipients, subject, body, node,smtp_from_domain,smtp_server, smtp_port, meme_path=None):
    smtp_from = f"{node}@{smtp_from_domain}"
    msg = construct_email_message(smtp_from, smtp_recipients, subject, body, meme_path)

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.sendmail(smtp_from, smtp_recipients, msg.as_string())
        server.quit()
        logging.info(f"Email sent to {', '.join(smtp_recipients)}")
    except Exception as e:
        logging.error(f"Email sending failed to {', '.join(smtp_recipients)}: {e}")


# Function to construct email message with an embedded image
def construct_email_message(smtp_from, smtp_recipients, subject, body, meme_path=None):
    # Create a MIMEMultipart message to handle both HTML and image content
    msg = MIMEMultipart('related')
    msg["From"] = smtp_from
    msg["To"] = ", ".join(smtp_recipients)
    msg["Subject"] = subject

    # 1) Escape the body so that any < or > won't be interpreted as HTML tags.
    safe_body = html.escape(body)

    # 2) Convert newlines to <br> for nicer formatting in HTML emails.
    safe_body_html = safe_body.replace("\n", "<br>")

    # 3) Wrap it in some HTML. You can also use <pre> if you want to preserve spacing exactly.
    html_body = f"""
    <html>
        <body>
            <p>{safe_body_html}</p>
            {"<img src='cid:meme_image' alt='Meme'>" if meme_path else ""}
        </body>
    </html>
    """

    # Attach the HTML body to the email
    msg.attach(MIMEText(html_body, 'html'))

    # Attach the image if the meme_path is provided
    if meme_path:
        with open(meme_path, 'rb') as img_file:
            meme_data = img_file.read()
            image_part = MIMEImage(meme_data)
            image_part.add_header('Content-ID', '<meme_image>')
            image_part.add_header('Content-Disposition', 'inline', filename='meme.jpg')
            msg.attach(image_part)

    return msg
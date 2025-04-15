import os
import requests
import logging
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def send_email(recipient_email, subject, html_content, text_content=None):
    """
    Send an email using the Mailgun API.
    
    Args:
        recipient_email (str): The email address of the recipient
        subject (str): The subject of the email
        html_content (str): The HTML content of the email
        text_content (str, optional): The plain text content (fallback for non-HTML clients)
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    # If no text content provided, create a simple version from the HTML
    if text_content is None:
        # Very basic HTML to text conversion (a proper implementation would use a library)
        text_content = html_content.replace('<br>', '\n').replace('</p>', '\n\n')
        # Remove all other HTML tags
        import re
        text_content = re.sub('<[^<]+?>', '', text_content)
    
    try:
        api_key = settings.MAILGUN_API_KEY
        domain = settings.MAILGUN_DOMAIN
        
        if not api_key or not domain:
            logger.error("Missing Mailgun API key or domain.")
            return False
        
        response = requests.post(
            f"https://api.mailgun.net/v3/{domain}/messages",
            auth=("api", api_key),
            data={
                "from": f"InfoAmazonia <no-reply@{domain}>",
                "to": recipient_email,
                "subject": subject,
                "text": text_content,
                "html": html_content
            }
        )
        
        if response.status_code == 200:
            logger.info(f"Email sent successfully to {recipient_email}")
            return True
        else:
            logger.error(f"Failed to send email. Status: {response.status_code}, Response: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        return False

def send_password_reset_email(email, reset_link):
    """
    Send password reset email with token link.
    
    Args:
        email (str): The email address of the admin user
        reset_link (str): The password reset link with token
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    subject = "InfoAmazonia Admin Password Reset"
    
    html_content = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>You requested a password reset for your InfoAmazonia Admin account.</p>
        <p>Click the link below to reset your password:</p>
        <p><a href="{reset_link}">Reset Password</a></p>
        <p>If you did not request a password reset, please ignore this email.</p>
        <p>The link will expire in 30 minutes.</p>
        <br>
        <p>Best regards,</p>
        <p>InfoAmazonia Team</p>
    </body>
    </html>
    """
    
    return send_email(email, subject, html_content)
from celery import shared_task
from utils.helpers import SendEmail
from django.conf import settings


@shared_task(name="send_otp_email_for_registration")
def send_registration_email_verification(
    email=None, last_name=None, verification_link=None
):
    template = "email_alerts/verification_code.html"
    subject = "Email Verification"
    return SendEmail(
        template=template,
        subject=subject,
        to_emails=[email],
        context=dict(verification_link=verification_link, last_name=last_name),
    ).send()


@shared_task(name="password_reset_email_task")
def send_password_reset_email(reset_code=None, email=None, last_name=None):
    template = "email_alerts/password_reset.html"
    subject = "Password Reset Code"
    return SendEmail(
        template=template,
        subject=subject,
        to_emails=[email],
        context=dict(reset_code=reset_code, last_name=last_name),
    ).send()


@shared_task(name="send_sms_notification")
def send_sms_notification(phone_no=None, message=None):
    if settings.ENV.lower() == "ci":
        return None
    import requests

    url = "https://sms.hollatags.com/api/send/"
    payload = {
        "user": settings.SMS_USER,
        "pass": settings.SMS_PASSWORD,
        "from": "V BANK",
        "to": phone_no,
        "msg": message,
    }
    print("send_sms_notification>>", message)
    response = requests.request("POST", url, data=payload)
    if response.ok:
        return response.text

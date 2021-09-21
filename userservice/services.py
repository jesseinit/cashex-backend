import random
import uuid
from datetime import datetime as dt
from typing import Dict

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from utils.exceptions import UnavailableResourceException
from utils.helpers import (
    CacheManager,
    ChannelManager,
    ResponseManager,
    TokenManager,
    VDFAuth,
)

from userservice.models import User, UserDevices
from userservice.tasks import (
    send_password_reset_email,
    send_registration_email_verification,
    send_sms_notification,
)


class AccountManagerService:
    def perform_bvn_enquiry(bvn_number: int = None, mobile_number: str = None) -> Dict:
        """Perfom BVN Enquiry"""

        enquiry_response = VDFAuth.validate_bvn_or_bank(
            entity_type="bvn", entity_value=bvn_number
        )

        reg_token = uuid.uuid4().hex
        otp = random.randint(1001, 9999)
        CacheManager.set_key(
            f"user.registration.session:{reg_token}",
            {
                "bvn": bvn_number,
                "reg_token": reg_token,
                "otp": str(otp),
                "is_email_verified": False,
                "is_otp_verified": False,
                "mobile_number": mobile_number,
                **enquiry_response,
            },
            timeout=86400,
        )

        if not settings.IS_PROD_ENV:
            send_sms_notification(
                phone_no=mobile_number,
                message=f"Your Cash Exchange verification code is {otp}",
            )
        else:
            send_sms_notification.delay(
                phone_no=mobile_number,
                message=f"Your Cash Exchange verification code is {otp}",
            )

        return {
            "bvn": bvn_number,
            "data": enquiry_response,
            "reg_token": reg_token,
        }

    def verify_registration_session_otp(reg_token: str = None, otp: str = None) -> bool:
        """Verfies the OTP sent to user during BVN/Bank Enquiry"""
        cached_enquiry = CacheManager.retrieve_key(
            f"user.registration.session:{reg_token}"
        )
        if cached_enquiry["otp"] != otp:
            raise ValidationError(
                {"error": {"otp": ["Incorrect OTP entered. Confirm and Retry"]}}
            )
        cached_enquiry["is_otp_verified"] = True
        CacheManager.set_key(
            f"user.registration.session:{reg_token}", cached_enquiry, timeout=21600
        )
        return True

    def verify_registration_session_email(reg_token: str = None) -> bool:
        registration_session = CacheManager.retrieve_key(
            f"user.registration.session:{reg_token}"
        )
        data_payload = {
            "event": "registration.updated",
            "body": {"email_verified": True},
        }
        registration_session["is_email_verified"] = True
        CacheManager.set_key(
            f"user.registration.session:{reg_token}", registration_session
        )
        ChannelManager.ws_publish(
            channel=f"registration_{reg_token}", payload=data_payload
        )

        return reg_token

    def perform_account_enquiry(
        acct_number: int = None, mobile_number: str = None
    ) -> Dict:
        """Perfom Account Enquiry"""
        enquiry_response = VDFAuth.validate_bvn_or_bank(
            entity_type="account", entity_value=acct_number
        )

        reg_token = uuid.uuid4().hex
        otp = random.randint(1001, 9999)

        CacheManager.set_key(
            f"user.registration.session:{reg_token}",
            {
                "account_number": acct_number,
                "reg_token": reg_token,
                "otp": str(otp),
                "is_email_verified": False,
                "is_otp_verified": False,
                "mobile_number": mobile_number,
                **enquiry_response,
            },
            timeout=86400,
        )

        if not settings.IS_PROD_ENV:
            send_sms_notification(
                phone_no=mobile_number,
                message=f"Your Cash Exchange verification code is {otp}",
            )
        else:
            send_sms_notification.delay(
                phone_no=mobile_number,
                message=f"Your Cash Exchange verification code is {otp}",
            )

        return {
            "account_number": acct_number,
            "data": enquiry_response,
            "reg_token": reg_token,
        }

    def process_pre_registration(
        reg_token: str = None,
        email_address: str = None,
        reg_mode: str = None,
    ) -> Dict:
        """Update registration session with Pre-registration values"""
        registration_session = CacheManager.retrieve_key(
            f"user.registration.session:{reg_token}"
        )

        registration_session.update(
            dict(email_address=email_address, reg_mode=reg_mode)
        )

        CacheManager.set_key(
            f"user.registration.session:{reg_token}",
            registration_session,
            timeout=21600,
        )

        verify_link = f"{settings.BACKEND_URL}/email-verification/{reg_token}"
        if not settings.IS_PROD_ENV:
            send_registration_email_verification(
                email=email_address,
                last_name=registration_session["lastname"].title(),
                verification_link=verify_link,
            )
        else:
            send_registration_email_verification.delay(
                email=email_address,
                last_name=registration_session["lastname"].title(),
                verification_link=verify_link,
            )

        return {
            "reg_token": reg_token,
            "email_address": email_address,
            "reg_mode": reg_mode,
        }

    def process_post_registration(reg_token: str = None, password: str = None) -> Dict:
        cache_data = CacheManager.retrieve_key(f"user.registration.session:{reg_token}")
        user_data = {
            "first_name": cache_data["firstname"].title(),
            "last_name": cache_data["lastname"].title(),
            "email": cache_data["email_address"],
            "mobile_number": cache_data["mobile_number"],
            "bvn_number": cache_data.get("bvn"),
            "dob": dt.strptime(cache_data["dob"], "%d-%b-%Y"),
            "account_type": None,
            "reg_mode": cache_data["reg_mode"],
            "password": make_password(password),
            "account_meta": cache_data,
        }

        user_instance, is_created = User.objects.get_or_create(
            email=user_data["email"],
            mobile_number=user_data["mobile_number"],
            defaults=user_data,
        )

        if is_created is False:
            raise ValidationError(
                {
                    "email": [
                        "An account with either this email or phone number already exists"
                    ]
                }
            )
        CacheManager.delete_key(f"user.registration.session:{reg_token}")

        return {
            "id": user_instance.id,
            "first_name": user_instance.first_name,
            "last_name": user_instance.last_name,
        }


class AuthenticationService:
    """Service class that handles authentication"""

    @staticmethod
    def perform_local_auth(**serialized_data):
        password = serialized_data["password"]
        email_or_phone = serialized_data["email_or_phone"]
        device = serialized_data.get("device")
        coordinates = serialized_data.get("coordinates")

        user_instance = User.objects.filter(
            Q(email=email_or_phone) | Q(mobile_number=email_or_phone)
        ).first()

        if not user_instance:
            raise AuthenticationFailed({"error": "Login Credentials is not correct"})

        is_valid_password = check_password(password, user_instance.password)

        if not is_valid_password:
            raise AuthenticationFailed({"error": "Login Credentials is not correct"})

        user_instance.update(
            latitude=coordinates["latitude"],
            longitude=coordinates["longitude"],
            last_login=timezone.now(),
        )

        user_device = user_instance.get_device()

        if not user_device:
            UserDevices.objects.update_or_create(user=user_instance, defaults=device)

        token = TokenManager.sign_token(
            payload={
                "uid": user_instance.id,
            }
        )

        return {
            "token": token,
            "user_info": {
                "first_name": user_instance.first_name,
                "last_name": user_instance.last_name,
                "image_url": user_instance.image_url,
                "reg_mode": user_instance.reg_mode,
                "account_type": user_instance.account_type,
            },
        }

    def logout_user(request):
        user = request.user
        token = request.headers.get("authorization").split(" ")[1]
        black_listed_tokens = CacheManager.retrieve_key("blacklisted_tokens")
        backlist_data = {
            "user_id": user.id,
            "token": token,
            "logout_at": timezone.now(),
        }
        if black_listed_tokens is None:
            black_listed_tokens = []
            black_listed_tokens.append(backlist_data)
            CacheManager.set_key("blacklisted_tokens", black_listed_tokens)
            return backlist_data

        invalid_tokens = [
            invalid_token["token"]
            for invalid_token in black_listed_tokens
            if invalid_token["user_id"] == user.id
        ]

        if token in invalid_tokens:
            raise ValidationError({"error": "You are already logged out"})

        black_listed_tokens.append(backlist_data)
        CacheManager.set_key("blacklisted_tokens", black_listed_tokens)

        return backlist_data

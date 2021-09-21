import jwt
from django.conf import settings
from django.utils.timezone import datetime
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from utils.helpers import TokenManager, UsersAvailabilityManager, ResponseManager

from userservice.models import User


class JSONWebTokenAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        try:
            bearer_str, token = get_authorization_header(request).decode().split()

            if not bearer_str:
                raise exceptions.AuthenticationFailed(
                    {
                        "error": "Authentication Failed",
                        "message": "Bearer String Not Set",
                    }
                )
            payload = TokenManager.decode_token(token)
            user = User.objects.filter(id=payload["uid"]).first()
        except (jwt.DecodeError, IndexError, KeyError, ValueError):
            raise exceptions.AuthenticationFailed(
                {
                    "error": "Authentication Failed",
                    "message": "Cannot validate your access credentials",
                }
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed(
                {"error": "Authentication Failed", "message": "Token has expired"}
            )

        if not user:
            raise exceptions.AuthenticationFailed(
                {
                    "error": "Authentication Failed",
                    "message": "Cannot validate your access credentials",
                }
            )
        # Update user's last seen
        UsersAvailabilityManager.set_user_last_seen(user)
        return (user, payload)

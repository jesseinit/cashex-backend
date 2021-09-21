from rest_framework import exceptions, permissions
from utils.helpers import CacheManager


class IsTokenBlackListed(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.headers.get("authorization"):
            try:
                token = "".join(request.headers.get("authorization").split())[6:]
                user_id = request.user.id
                black_listed_tokens = CacheManager.retrieve_key("blacklisted_tokens")
                if black_listed_tokens is not None:
                    invalid_tokens = [
                        invalid_token["token"]
                        for invalid_token in black_listed_tokens
                        if invalid_token["user_id"] == user_id
                    ]
                    if token in invalid_tokens:
                        raise exceptions.PermissionDenied(
                            {"error": "Session has expired. Please login again."}
                        )
                    else:
                        return True
                return True
            except (KeyError, IndexError, ValueError):
                raise exceptions.PermissionDenied(
                    {
                        "error": "You do not have permission to perform this action.",
                    }
                )
        return False

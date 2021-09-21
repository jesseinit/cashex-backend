from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from userservice.models import User
import jwt


@database_sync_to_async
def get_user(query_string):
    try:
        _, token_key = query_string.decode().split("=")
        payload = jwt.decode(token_key, settings.SECRET_KEY, algorithms=["HS256"])
        user = User.objects.filter(id=payload["uid"]).first()
        return user or AnonymousUser()
    except Exception:
        return AnonymousUser()


class TokenAuthMiddlewareInstance:
    """
    Yeah, this is black magic:
    https://github.com/django/channels/issues/1399
    """

    def __init__(self, scope, middleware):
        self.middleware = middleware
        self.scope = dict(scope)
        self.inner = self.middleware.inner

    async def __call__(self, receive, send):
        query_string = self.scope["query_string"]
        user = await get_user(query_string)
        self.scope["user"] = user
        inner = self.inner(self.scope)
        return await inner(receive, send)


class TokenAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    def __call__(self, scope):
        return TokenAuthMiddlewareInstance(scope, self)


def TokenAuthMiddlewareStack(inner):
    return TokenAuthMiddleware(AuthMiddlewareStack(inner))

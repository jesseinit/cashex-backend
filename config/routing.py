from channels.routing import ProtocolTypeRouter, URLRouter
from transactionservice.authentication import TokenAuthMiddlewareStack
import transactionservice.routing
import userservice.routing

ws_routes = [
    *transactionservice.routing.websocket_urlpatterns,
    *userservice.routing.websocket_urlpatterns,
]

application = ProtocolTypeRouter(
    {"websocket": TokenAuthMiddlewareStack(URLRouter(ws_routes))}
)

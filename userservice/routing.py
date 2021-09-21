from django.urls import re_path

from userservice.consumers import RegistrationConsumer

websocket_urlpatterns = [
    re_path(r"ws/registration/(?P<reg_code>\w+)$", RegistrationConsumer),
]

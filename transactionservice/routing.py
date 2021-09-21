from django.urls import re_path

from transactionservice.consumers import TransactionConsumer

websocket_urlpatterns = [
    re_path(r"ws/transaction/(?P<request_id>\w+)/$", TransactionConsumer),
]

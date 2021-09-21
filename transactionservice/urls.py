from django.conf.urls import url, re_path
from django.urls import include
from rest_framework.routers import DefaultRouter

from transactionservice.views import (
    ExchangeRequestViewset,
    ExchangeTransactionsRatingsViewset,
    ExchangeTransactionsViewset,
)

router = DefaultRouter(trailing_slash=False)
router.register(
    r"exchange-request", ExchangeRequestViewset, basename="exchange-request"
)
router.register(
    r"exchange-transaction",
    ExchangeTransactionsViewset,
    basename="exchange-transaction",
)
router.register(
    r"exchange-rating",
    ExchangeTransactionsRatingsViewset,
    basename="exchange-rating",
)
urlpatterns = [
    re_path(r"", include(router.urls)),
]

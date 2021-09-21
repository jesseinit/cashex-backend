from django.conf.urls import url, re_path
from django.urls import include
from rest_framework.routers import DefaultRouter

from paymentservice.views import ExchangePaymentViewset

router = DefaultRouter(trailing_slash=False)
router.register(
    r"exchange-payment", ExchangePaymentViewset, basename="exchange-payment"
)

urlpatterns = [
    re_path(r"", include(router.urls)),
]

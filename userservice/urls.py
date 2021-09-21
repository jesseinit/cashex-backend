from django.conf.urls import url, re_path
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from userservice.views import (
    BankAcctCustomerOnBoardingViewset,
    DeviceResetViewset,
    BVNCustomerOnboardingViewset,
    PaswordResetViewset,
    LoginCustomerViewset,
    UserProfileViewset,
)

router = DefaultRouter(trailing_slash=False)
router.register(
    r"auth/bvn", BVNCustomerOnboardingViewset, basename="bvn-user-onboarding"
)
router.register(
    r"auth/bank", BankAcctCustomerOnBoardingViewset, basename="bank-user-onboarding"
)
router.register(r"auth", LoginCustomerViewset, basename="user-login")
router.register(r"user/profile", UserProfileViewset, basename="user-resource")
router.register(r"user/password-reset", PaswordResetViewset, basename="password-reset")
router.register(r"user/device-reset", DeviceResetViewset, basename="device-reset")

urlpatterns = [
    re_path(r"", include(router.urls)),
]

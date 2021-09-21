from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.views import APIView
from utils.helpers import ResponseManager

from userservice.serializers import (
    EmailOTPVerifySerializer,
    EmailVerificationSerializer,
    FinalizeDeviceResetSerializer,
    FinalizePasswordResetSerializer,
    GenericLoginUserSerializer,
    InitiateDeviceResetSerializer,
    InitiatePasswordResetSerializer,
    PostRegistrationSerializer,
    PreRegistrationSerializer,
    ResolveBankSerializer,
    ResolveBVNSerializer,
    UserProfileSerializer,
    ValidatePasswordResetCodeSerializer,
    VerifyOTPSerializer,
)
from userservice.services import AccountManagerService, AuthenticationService


class BVNCustomerOnboardingViewset(viewsets.ViewSet):
    """ Create a new customer account """

    permission_classes = ()
    authentication_classes = ()

    @action(detail=False, methods=["post"], url_path="enquire")
    def enquire_bvn(self, request):
        """ Perfom BVN Enquiry """
        serialized_data = ResolveBVNSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        service_response = AccountManagerService.perform_bvn_enquiry(
            bvn_number=serialized_data.data["bvn"],
            mobile_number=serialized_data.data["mobile_number"],
        )
        return ResponseManager.handle_response(data=service_response)

    @action(detail=False, methods=["post"], url_path="verify")
    def verify_otp(self, request):
        """ Verify BVN OTP """
        serialized_data = VerifyOTPSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        service_response = AccountManagerService.verify_registration_session_otp(
            reg_token=serialized_data.data["reg_token"], otp=serialized_data.data["otp"]
        )
        return ResponseManager.handle_response(
            data={"is_otp_verified": service_response}
        )

    @action(detail=False, methods=["post"], url_path="pre-registration")
    def pre_registration(self, request):
        """ Checks that the BVN is valid """
        serialized_data = PreRegistrationSerializer(
            data=request.data, context={"request": request}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        service_response = AccountManagerService.process_pre_registration(
            reg_token=serialized_data.data["reg_token"],
            email_address=serialized_data.data["email_address"],
            reg_mode=serialized_data.data["reg_mode"],
        )
        return ResponseManager.handle_response(data=service_response)

    @action(detail=False, methods=["post"], url_path="validate-email-otp")
    def email_otp_validation(self, request):
        """ Validate Email OTP """
        serialized_data = EmailOTPVerifySerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data={"is_email_verified": True})

    @action(detail=False, methods=["post"], url_path="post-registration")
    def post_registration(self, request):
        """ Sets password and create account """
        serialized_data = PostRegistrationSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        service_response = AccountManagerService.process_post_registration(
            reg_token=serialized_data.data["reg_token"],
            password=serialized_data.data["password"],
        )
        return ResponseManager.handle_response(data=service_response, status=201)


class BankAcctCustomerOnBoardingViewset(viewsets.ViewSet):
    permission_classes = ()
    authentication_classes = ()

    @action(detail=False, methods=["post"], url_path="enquire")
    def bank_enquire(self, request):
        """ Checks that the Bank details is valid """
        serialized_data = ResolveBankSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        service_response = AccountManagerService.perform_account_enquiry(
            acct_number=serialized_data.data["acct_number"],
            mobile_number=serialized_data.data["mobile_number"],
        )
        return ResponseManager.handle_response(data=service_response)

    @action(detail=False, methods=["post"], url_path="verify")
    def verify_otp(self, request):
        """ Verify the OTP sent from BVN Enquiry """
        serialized_data = VerifyOTPSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        service_response = AccountManagerService.verify_registration_session_otp(
            reg_token=serialized_data.data["reg_token"], otp=serialized_data.data["otp"]
        )
        return ResponseManager.handle_response(
            data={"is_otp_verified": service_response}
        )

    @action(detail=False, methods=["post"], url_path="pre-registration")
    def pre_registration(self, request):
        serialized_data = PreRegistrationSerializer(
            data=request.data, context={"request": request}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )

        service_response = AccountManagerService.process_pre_registration(
            reg_token=serialized_data.data["reg_token"],
            email_address=serialized_data.data["email_address"],
            reg_mode=serialized_data.data["reg_mode"],
        )

        return ResponseManager.handle_response(data=service_response)

    @action(detail=False, methods=["post"], url_path="validate-email-otp")
    def validate_email(self, request):
        serialized_data = EmailOTPVerifySerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data={"is_email_verified": True})

    @action(detail=False, methods=["post"], url_path="post-registration")
    def post_registration(self, request):
        serialized_data = PostRegistrationSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        service_response = AccountManagerService.process_post_registration(
            reg_token=serialized_data.data["reg_token"],
            password=serialized_data.data["password"],
        )
        return ResponseManager.handle_response(data=service_response, status=201)


class LoginCustomerViewset(viewsets.ViewSet):
    permission_classes = ()
    authentication_classes = ()

    @action(detail=False, methods=["post"], url_path="login")
    def login_user(self, request):
        serialized_data = GenericLoginUserSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        service_response = AuthenticationService.perform_local_auth(
            **serialized_data.data
        )
        return ResponseManager.handle_response(data=service_response)


class UserProfileViewset(viewsets.ViewSet):
    @action(detail=False, methods=["get"], url_path="retrieve")
    def retrieve_user_profile(self, request):
        serialized_data = UserProfileSerializer(request.user)
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(detail=False, methods=["patch"], url_path="update")
    def patch_user_profile(self, request):
        serialized_data = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        serialized_data.save()
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(detail=False, methods=["post"], url_path="logout")
    def logout_user_profile(self, request):
        service_response = AuthenticationService.logout_user(request)
        return ResponseManager.handle_response(data=service_response)


class PaswordResetViewset(viewsets.ViewSet):
    permission_classes = ()
    authentication_classes = ()

    @action(detail=False, methods=["post"], url_path="initiate")
    def initiate_password_reset(self, request):
        serialized_data = InitiatePasswordResetSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(
            message="Please check your email for reset instructions 🤗", data=None
        )

    @action(detail=False, methods=["post"], url_path="validate-reset-code")
    def validate_reset_code(self, request):
        serialized_data = ValidatePasswordResetCodeSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(
            message="Reset code was confirmed. ❤", data=None
        )

    @action(detail=False, methods=["post"], url_path="finalize")
    def finalize_password_reset(self, request):
        serialized_data = FinalizePasswordResetSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(
            message="Password reset has been completed 🚀", data=None
        )


class EmailVerficationView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = "pages/verify_email_registration.html"
    permission_classes = ()
    authentication_classes = ()

    def get(self, request, *args, **kwargs):
        reg_token = kwargs.get("regcode")

        serialized_data = EmailVerificationSerializer(data={"reg_token": reg_token})
        if not serialized_data.is_valid():
            return ResponseManager.handle_template_response(
                {}, "pages/404.html", status=404
            )

        AccountManagerService.verify_registration_session_email(
            reg_token=serialized_data.data["reg_token"]
        )

        return ResponseManager.handle_template_response(
            {
                "page_title": "Verify Email - Cash Exchange",
            },
            self.template_name,
        )


class DeviceResetViewset(viewsets.ViewSet):
    permission_classes = ()
    authentication_classes = ()

    @action(detail=False, methods=["post"], url_path="initiate")
    def initiate_device_reset(self, request):
        serialized_data = InitiateDeviceResetSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(
            message="Please check your phone for OTP 🤗", data=None
        )

    @action(detail=False, methods=["post"], url_path="finalize")
    def finalize_device_reset(self, request):
        serialized_data = FinalizeDeviceResetSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(
            message="Device reset completed. Kindly login.", data=None
        )

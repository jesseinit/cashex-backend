import random
import uuid
from datetime import datetime as dt

import cloudinary.uploader
import phonenumbers
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.validators import validate_email
from django.db.models import Avg, Count, Sum
from django.db.models.functions import Coalesce
from drf_extra_fields.fields import Base64ImageField
from rest_framework import serializers
from transactionservice.models import ExchangeTransactions, TransactionUserRatings
from utils.helpers import CacheManager, VDFAuth

from userservice.models import User, UserDevices
from userservice.tasks import send_password_reset_email, send_sms_notification


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that takes an additional `fields` argument that
    controls which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields = kwargs.pop("fields", None)

        # Instantiate the superclass normally
        super().__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)


class FieldValidators:
    @staticmethod
    def validate_mobile_number(mobile_number):
        try:
            validated_no = phonenumbers.parse(mobile_number, "NG")
            if phonenumbers.is_valid_number(validated_no) is False:
                raise serializers.ValidationError("Mobile number is not valid")
        except phonenumbers.phonenumberutil.NumberParseException:
            raise serializers.ValidationError("Mobile number is not valid")
        return mobile_number

    @staticmethod
    def validate_registration_session(reg_token):
        cached_registration_session = CacheManager.retrieve_key(
            f"user.registration.session:{reg_token}"
        )
        if not cached_registration_session:
            raise serializers.ValidationError("Registration session not found")

    @staticmethod
    def validate_existing_user_email(email_address):
        email_address = email_address.lower()
        user = User.objects.filter(email=email_address).first()
        if user:
            raise serializers.ValidationError(
                "A user has already registered with this email address"
            )
        return email_address


class ResolveBVNSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(
        min_length=11,
        max_length=11,
        validators=[FieldValidators.validate_mobile_number],
    )
    bvn = serializers.CharField(min_length=11, max_length=11)

    def validate(self, validated_data):
        user = User.objects.filter(
            mobile_number=validated_data["mobile_number"]
        ).exists()
        if user:
            raise serializers.ValidationError(
                {
                    "mobile_number": [
                        "A user has already registered with this phone number"
                    ]
                }
            )
        return validated_data


class VerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField(required=True, min_length=4, max_length=4)
    reg_token = serializers.CharField(
        validators=[FieldValidators.validate_registration_session]
    )


class PreRegistrationSerializer(serializers.Serializer):
    reg_mode = serializers.ChoiceField(choices=["Bvn", "Bank"])
    email_address = serializers.EmailField(
        validators=[FieldValidators.validate_existing_user_email]
    )
    reg_token = serializers.CharField(
        validators=[FieldValidators.validate_registration_session]
    )

    def validate(self, validated_data):
        reg_token = validated_data["reg_token"]
        registration_session = CacheManager.retrieve_key(
            f"user.registration.session:{reg_token}"
        )

        if registration_session["is_otp_verified"] is False:
            raise serializers.ValidationError(
                {"reg_token": ["OTP has not been verified"]}
            )

        if registration_session["reg_token"] != reg_token:
            raise serializers.ValidationError(
                {"reg_token": ["Could not validate the Registration Token"]}
            )

        return validated_data


class EmailOTPVerifySerializer(serializers.Serializer):
    reg_token = serializers.CharField(
        validators=[FieldValidators.validate_registration_session]
    )

    def validate(self, validated_data):
        reg_token = validated_data["reg_token"]
        registration_session = CacheManager.retrieve_key(
            f"user.registration.session:{reg_token}"
        )
        if registration_session["is_email_verified"] is False:
            raise serializers.ValidationError(
                {
                    "email_address": [
                        "Your email has not been verified. Check your mail box and retry."
                    ]
                }
            )
        return validated_data


class PostRegistrationSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=8, max_length=16)
    confirm_password = serializers.CharField(
        min_length=8, max_length=16, write_only=True
    )
    reg_token = serializers.CharField(
        validators=[FieldValidators.validate_registration_session]
    )

    def validate(self, validated_data):
        password = validated_data["password"]
        confirm_password = validated_data["confirm_password"]
        if password != confirm_password:
            raise serializers.ValidationError(
                {"password": ["Passwords does not match"]}
            )
        reg_token = validated_data["reg_token"]
        cache_data = CacheManager.retrieve_key(f"user.registration.session:{reg_token}")

        if cache_data["is_email_verified"] is False:
            raise serializers.ValidationError(
                {"reg_token": ["Your email has not been verified."]}
            )

        return validated_data


class ResolveBankSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(
        required=True,
        min_length=11,
        max_length=11,
        validators=[FieldValidators.validate_mobile_number],
    )
    acct_number = serializers.CharField(required=True, min_length=10, max_length=11)

    def validate_mobile_number(self, mobile_number):
        user = User.objects.filter(mobile_number=mobile_number).exists()
        if user:
            raise serializers.ValidationError(
                "A user has already registered with this phone number"
            )
        return mobile_number


class BankOTPVerifySerializer(serializers.Serializer):
    otp = serializers.CharField(required=True, min_length=4, max_length=4)
    reg_token = serializers.CharField(required=True)


class BankPostRegistrationSerializer(serializers.Serializer):
    reg_token = serializers.CharField(
        validators=[FieldValidators.validate_registration_session]
    )

    def validate(self, validated_data):
        reg_token = validated_data["reg_token"]
        cache_data = CacheManager.retrieve_key(f"reg_token:{reg_token}")
        if not cache_data:
            raise serializers.ValidationError(
                {
                    "reg_token": [
                        "Please provide an Email adress during Pre Registration"
                    ]
                }
            )
        if cache_data["is_email_verified"] is False:
            raise serializers.ValidationError(
                {"reg_token": ["Your email has not been verified."]}
            )
        user_data = {
            "first_name": cache_data["user.registration.session"]["user"][
                "firstname"
            ].title(),
            "last_name": cache_data["user.registration.session"]["user"][
                "lastname"
            ].title(),
            "email": cache_data["email_address"],
            "mobile_number": cache_data["mobile_number"],
            "dob": dt.strptime(cache_data["dob"], "%d-%b-%Y"),
            "account_type": cache_data["account_type"],
            "reg_mode": "Bank",
            "password": make_password(cache_data["mobile_number"]),
            "account_meta": cache_data,
        }
        user_instance, is_created = User.objects.get_or_create(
            email=user_data["email"],
            mobile_number=user_data["mobile_number"],
            defaults=user_data,
        )
        if is_created is False:
            raise serializers.ValidationError(
                {
                    "email": [
                        "An Account with either this email or phone number already exists"
                    ]
                }
            )
        setattr(self, "user_instance", user_instance)
        CacheManager.delete_key(f"reg_token:{reg_token}")
        CacheManager.delete_key(f"user.registration.session:{reg_token}")
        return validated_data

    def to_representation(self, instance):
        rep = instance
        user_data = self.user_instance
        rep["user_data"] = {"id": user_data.id, "last_name": user_data.last_name}
        return rep


class PhoneOrEmailField(serializers.Field):
    def to_representation(self, email_or_phone):
        return email_or_phone.lower()

    def to_internal_value(self, email_or_phone):
        if "@" in email_or_phone:
            validate_email(email_or_phone)
            return email_or_phone.strip()
        try:
            validated_no = phonenumbers.parse(email_or_phone, "NG")
            if phonenumbers.is_valid_number(validated_no) is False:
                raise serializers.ValidationError("Mobile number is not valid")
        except phonenumbers.phonenumberutil.NumberParseException:
            raise serializers.ValidationError("Mobile number is not valid")
        return email_or_phone.strip()


class UserDeviceFields(serializers.Serializer):
    name = serializers.CharField(min_length=2)
    device_id = serializers.CharField(min_length=5)
    registration_id = serializers.CharField(min_length=20)
    type = serializers.ChoiceField(choices=["android", "ios"])


class UserCoordinatesFields(serializers.Serializer):
    latitude = serializers.FloatField(max_value=90, min_value=-90)
    longitude = serializers.FloatField(max_value=180, min_value=-180)


class GenericLoginUserSerializer(serializers.Serializer):
    email_or_phone = PhoneOrEmailField(required=True)
    password = serializers.CharField(required=True, min_length=8, max_length=16)
    coordinates = UserCoordinatesFields(required=True)
    device = UserDeviceFields()


class BankAcctLoginUserSerializer(serializers.Serializer):
    password = serializers.CharField(required=True, min_length=8, max_length=16)
    email_or_phone = serializers.CharField(required=True)
    coordinates = UserCoordinatesFields(required=True)

    def validate(self, validated_data):
        auth_response = VDFAuth.login_user(
            username=validated_data["email_or_phone"],
            password=validated_data["password"],
        )
        self.auth_response = auth_response

        if not auth_response:
            raise serializers.ValidationError(
                {"email_or_phone": "Login Credentials is not correct"}
            )
        return validated_data

    def to_representation(self, instance):
        instance["auth_response"] = self.auth_response
        return instance


class UserProfileSerializer(DynamicFieldsModelSerializer):
    device_id = serializers.ReadOnlyField()
    password = serializers.CharField(write_only=True, required=False)
    transaction_summary = serializers.SerializerMethodField()
    display_name = serializers.CharField()
    image_url_update = Base64ImageField(write_only=True)

    class Meta:
        model = User
        exclude = ("account_meta",)

    def get_transaction_summary(self, user_instance):
        as_agent_qs = ExchangeTransactions.objects.filter(
            agent=user_instance, transaction_status="COMPLETED"
        )
        agent_stats = as_agent_qs.aggregate(
            total_volume=Coalesce(Sum("request_amount"), 0)
            + Coalesce(Sum("request_fees"), 0),
            txn_count=Count("agent"),
        )
        as_customer_qs = ExchangeTransactions.objects.filter(
            customer=user_instance, transaction_status="COMPLETED"
        )
        customer_stats = as_customer_qs.aggregate(
            total_volume=Coalesce(Sum("request_amount"), 0), txn_count=Count("customer")
        )
        user_ratings = TransactionUserRatings.objects.filter(
            rated_user=user_instance
        ).aggregate(average=Coalesce(Avg("user_rating"), 0))
        total_txn = agent_stats["txn_count"] + customer_stats["txn_count"]
        total_vol = agent_stats["total_volume"] + customer_stats["total_volume"]
        return dict(
            total_transactions=total_txn,
            total_volume=total_vol,
            avg_ratings=user_ratings["average"],
        )

    def validate_image_url_update(self, image_url):
        upload_response = cloudinary.uploader.upload(image_url)
        return upload_response.get("secure_url")

    def update(self, instance, validated_data):
        if instance.reg_mode == "Bvn":
            password = validated_data.get("password")
            update_payload = {
                "password": make_password(password) if password else instance.password,
                "image_url": validated_data.get("image_url_update", instance.image_url),
                "display_name": validated_data.get("display_name", instance.first_name),
                "address": validated_data.get("address", instance.address),
            }
            instance = instance.update(**update_payload)
            return instance
        update_payload = {
            "image_url": validated_data.get("image_url_update", instance.image_url),
            "display_name": validated_data.get("display_name", instance.first_name),
            "address": validated_data.get("address", instance.address),
        }
        instance.update(**update_payload)
        return instance


class InitiatePasswordResetSerializer(serializers.Serializer):
    email_address = serializers.EmailField()

    def validate_email_address(self, email_address):
        user = User.objects.filter(email=email_address, reg_mode="Bvn").first()
        if not user:
            raise serializers.ValidationError("No user with this email")
        self.user = user
        return email_address

    def validate(self, validated_data):
        email_address = validated_data["email_address"]
        reset_code = random.randint(100001, 999999)
        CacheManager.set_key(
            f"password:reset:{email_address}",
            {"reset_code": reset_code, "is_validated": False},
            timeout=60 * 30,
        )
        # Todo - Send user an email with reset code
        send_password_reset_email(
            reset_code=reset_code, email=email_address, last_name=self.user.last_name
        )
        return validated_data


class ValidatePasswordResetCodeSerializer(serializers.Serializer):
    reset_code = serializers.IntegerField(max_value=999999)
    email_address = serializers.EmailField()

    def validate(self, validated_data):
        email_address = validated_data["email_address"]
        reset_code = validated_data["reset_code"]
        cached_reset_data = CacheManager.retrieve_key(f"password:reset:{email_address}")
        if not cached_reset_data:
            raise serializers.ValidationError(
                {"reset_code": ["Reset code has exipired. Try again"]}
            )
        if cached_reset_data["reset_code"] != reset_code:
            raise serializers.ValidationError(
                {"reset_code": ["Reset code does not match. Confirm and try again"]}
            )
        CacheManager.set_key(
            f"password:reset:{email_address}",
            {"is_validated": True, "reset_code": cached_reset_data["reset_code"]},
        )
        return validated_data


class FinalizePasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(min_length=8)
    email_address = serializers.EmailField()

    def validate(self, validated_data):
        email_address = validated_data["email_address"]
        new_password = validated_data["new_password"]
        cached_reset_data = CacheManager.retrieve_key(f"password:reset:{email_address}")
        if not cached_reset_data:
            raise serializers.ValidationError(
                {"reset_code": ["Reset code has exipired. Try again"]}
            )
        if cached_reset_data["is_validated"] is False:
            raise serializers.ValidationError(
                {"reset_code": ["You have not provided the correct reset code."]}
            )
        user = User.objects.filter(email=email_address).first()
        user.update(password=make_password(new_password))
        CacheManager.delete_key(f"password:reset:{email_address}")
        return validated_data


class EmailVerificationSerializer(serializers.Serializer):
    reg_token = serializers.CharField(
        validators=[FieldValidators.validate_registration_session]
    )


class InitiateDeviceResetSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(required=True, min_length=11, max_length=11)
    device_id = serializers.CharField(min_length=5)

    def validate_mobile_number(self, mobile_number):
        mobile_number = mobile_number.strip()
        try:
            validated_no = phonenumbers.parse(mobile_number, "NG")
            if phonenumbers.is_valid_number(validated_no) is False:
                raise serializers.ValidationError("Mobile number is not valid")
        except phonenumbers.phonenumberutil.NumberParseException:
            raise serializers.ValidationError("Mobile number is not valid")
        user = User.objects.filter(mobile_number=mobile_number).first()
        if not user:
            raise serializers.ValidationError("No account matches your mobile number")

        return mobile_number

    def validate(self, validated_data):
        mobile_number = validated_data["mobile_number"]
        device_id = validated_data["device_id"]

        # Todo - Abstract to service
        otp = random.randint(1000, 9999)

        CacheManager.set_key(
            f"user.device_reset.{mobile_number}",
            {"otp": otp, "device_id": device_id},
            timeout=3600,
        )

        if not settings.IS_PROD_ENV:
            send_sms_notification(
                phone_no=mobile_number, message=f"Your device reset code is {otp}"
            )
        else:
            send_sms_notification.delay(
                phone_no=mobile_number, message=f"Your device reset code is {otp}"
            )

        return validated_data


class FinalizeDeviceResetSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(required=True, min_length=11, max_length=11)
    otp = serializers.CharField(required=True, min_length=4, max_length=4)
    device = UserDeviceFields()

    def validate_mobile_number(self, mobile_number):
        mobile_number = mobile_number.strip()
        try:
            validated_no = phonenumbers.parse(mobile_number, "NG")
            if phonenumbers.is_valid_number(validated_no) is False:
                raise serializers.ValidationError("Mobile number is not valid")
        except phonenumbers.phonenumberutil.NumberParseException:
            raise serializers.ValidationError("Mobile number is not valid")
        return mobile_number

    def validate(self, validated_data):
        mobile_number = validated_data["mobile_number"]
        otp = validated_data["otp"]
        device = validated_data["device"]

        cached_data = CacheManager.retrieve_key(f"user.device_reset.{mobile_number}")
        if not cached_data:
            raise serializers.ValidationError(
                {"mobile_number": "You have not initated device reset"}
            )

        if str(otp) != str(cached_data["otp"]):
            raise serializers.ValidationError(
                {"otp": "Incorrect OTP. Please confirm and retry"}
            )

        if device["device_id"] != cached_data["device_id"]:
            raise serializers.ValidationError({"device_id": "Device mismatch error"})

        user_instance = User.objects.get(mobile_number=mobile_number)
        UserDevices.objects.update_or_create(user=user_instance, defaults=device)
        CacheManager.delete_key(f"user.device_reset.{mobile_number}")

        return validated_data

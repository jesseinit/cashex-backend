from django.contrib.auth.models import AbstractBaseUser
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from utils.constants import DEFAULT_AVATAR_URL
from utils.model_helpers import BaseAbstractModel
from fcm_django.models import AbstractFCMDevice


class UserDevices(BaseAbstractModel, AbstractFCMDevice):
    class Meta:
        db_table = "UserDevices"
        indexes = [
            models.Index(
                fields=["state"],
            )
        ]


class UserManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(state="active")


class User(BaseAbstractModel, AbstractBaseUser):
    """
    Customer Model
    """

    class Meta:
        db_table = "User"
        indexes = [
            models.Index(
                fields=["state"],
            )
        ]

    ACCT_TYPE = [
        ("Agent", "Agent"),
        ("Customer", "Customer"),
    ]

    REG_MODE = [
        ("Bank", "Bank"),
        ("Bvn", "Bvn"),
    ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100, default=None, null=True)
    address = models.CharField(max_length=300, default=None, null=True)
    email = models.EmailField(max_length=100, unique=True)
    mobile_number = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=100)
    image_url = models.CharField(default=DEFAULT_AVATAR_URL, max_length=400)
    transaction_pin = models.CharField(max_length=4, null=True)
    bvn_number = models.CharField(max_length=11, null=True)
    dob = models.DateField()
    account_type = models.CharField(
        max_length=20, choices=ACCT_TYPE, null=True, default=None
    )
    reg_mode = models.CharField(max_length=20, choices=REG_MODE)
    latitude = models.FloatField(default=None, null=True)
    longitude = models.FloatField(default=None, null=True)
    account_meta = models.JSONField(default=dict, null=True, encoder=DjangoJSONEncoder)
    USERNAME_FIELD = "email"
    objects = UserManager()

    @property
    def device_id(self):
        device = self.get_device()
        return device.device_id if device else None

    def get_device(self):
        return self.userdevices_set.first()

    def send_push_notification(self, title=None, body=None, context: dict = None):
        if device := self.get_device():  # Walrus Operator Yaaayyy
            device.send_message(title=title, body=body, data=context)

    def __str__(self):
        return f"User >>> {self.email}"

    def __repr__(self):
        return f"User >>> {self.email}"

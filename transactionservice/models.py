from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

# from userservice.models import User
from django.conf import settings
from utils.model_helpers import BaseAbstractModel

# Create your models here.


class BaseManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(state="active")


class ExchangeRequestsQS(models.QuerySet):
    """ Custom query set to filter tudo states """

    def pending(self):
        return self.filter(request_status="PENDING", state="active").order_by(
            "-created_at"
        )

    def accepted(self):
        return self.filter(request_status="ACCEPTED", state="active").order_by(
            "-created_at"
        )

    def declined(self):
        return self.filter(request_status="DECLINED", state="active").order_by(
            "-created_at"
        )

    def everything(self):  # nameing this all was wasnt working
        return self.filter(state="active").order_by("-created_at")


class ExchangeRequests(BaseAbstractModel):
    """ This model stores all exchange requests"""

    REQUEST_STATUS = [
        ("PENDING", "PENDING"),
        ("ACCEPTED", "ACCEPTED"),
        ("DECLINED", "DECLINED"),
    ]

    request_status = models.CharField(
        max_length=20, choices=REQUEST_STATUS, default="PENDING"
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="The user that would process this request",
        related_name="request_agent",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        default=None,
        verbose_name="The user who is requesting for exchange",
        related_name="request_customer",
    )
    request_id = models.CharField(
        max_length=70, verbose_name="The request id generated at agents search"
    )

    request_meta = models.JSONField(default=dict, null=True, encoder=DjangoJSONEncoder)

    class Meta:
        db_table = "ExchangeRequests"
        indexes = [
            models.Index(
                fields=["state", "request_status", "request_id"],
            )
        ]

    objects = BaseManager()
    status = ExchangeRequestsQS().as_manager()

    def __str__(self):
        return f"ExchangeRequests >>> {self.id}"

    def __repr__(self):
        return f"ExchangeRequests >>> {self.id}"


class ExchangeTransactionsQS(models.QuerySet):
    """ Custom query set to filter tudo states """

    def in_progress(self):
        return self.filter(transaction_status="IN-PROGRESS", state="active").order_by(
            "-created_at"
        )

    def cancelled(self):
        return self.filter(transaction_status="CANCELLED", state="active").order_by(
            "-created_at"
        )

    def abandoned(self):
        return self.filter(transaction_status="ABANDONED", state="active").order_by(
            "-created_at"
        )

    def completed(self):
        return self.filter(transaction_status="COMPLETED", state="active").order_by(
            "-created_at"
        )

    def everything(self):
        return self.filter(state="active").order_by("-created_at")


class ExchangeTransactions(BaseAbstractModel):
    """ This model stores all exchange transactions"""

    TRANSACTION_STATUS = [
        ("IN-PROGRESS", "IN-PROGRESS"),
        ("CANCELLED", "CANCELLED"),
        ("ABANDONED", "ABANDONED"),
        ("COMPLETED", "COMPLETED"),
    ]

    CLOSING_AGENTS = [
        ("SYSTEM", "SYSTEM"),
        ("CUSTOMER", "CUSTOMER"),
        ("AGENT", "CUSTOMER"),
    ]

    transaction_status = models.CharField(max_length=20, choices=TRANSACTION_STATUS)
    closed_at = models.DateTimeField(default=None, null=True)
    closed_by = models.CharField(
        max_length=20, choices=CLOSING_AGENTS, null=True, default=None
    )
    cancellation_reason = models.CharField(max_length=600, null=True, default=None)
    request_amount = models.IntegerField()
    request_fees = models.IntegerField()
    request = models.ForeignKey(
        ExchangeRequests,
        on_delete=models.CASCADE,
        verbose_name="The request id for this exchange",
        related_name="transaction_request",
        null=True,
        default=None,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="The user who is requesting for exchange",
        related_name="transaction_customer",
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="The user who is fufiling exchange request",
        related_name="transaction_agent",
    )
    dest_latitude = models.FloatField(default=None, null=True)
    dest_longitude = models.FloatField(default=None, null=True)

    class Meta:
        db_table = "ExchangeTransactions"
        indexes = [
            models.Index(
                fields=["state", "transaction_status"],
            )
        ]

    objects = BaseManager()
    status = ExchangeTransactionsQS().as_manager()

    def __str__(self):
        return f"ExchangeTransactions >>> {self.id}"

    def __repr__(self):
        return f"ExchangeTransactions >>> {self.id}"


class TransactionUserRatings(BaseAbstractModel):
    """ Model for User Ratings for a Transaction """

    rating_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rating_user"
    )
    rated_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rated_user"
    )
    transaction = models.ForeignKey(ExchangeTransactions, on_delete=models.CASCADE)
    user_rating = models.PositiveIntegerField()

    objects = BaseManager()

    class Meta:
        db_table = "TransactionUserRatings"
        indexes = [
            models.Index(
                fields=["state"],
            )
        ]

    def __str__(self):
        return f"TransactionUserRatings>>>{self.transaction.id}"

    def __repr__(self):
        return f"TransactionUserRatings>>>{self.transaction.id}"

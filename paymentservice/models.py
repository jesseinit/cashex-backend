from django.db import models
from utils.model_helpers import BaseAbstractModel
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings

# Create your models here.


class BaseManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(state="active")


class TransactionPayments(BaseAbstractModel):
    """ This model stores all exchange requests"""

    PAYMENT_STATUS = [
        ("IN_ESCROW", "IN_ESCROW"),
        ("REVERSED", "REVERSED"),
        ("COMPLETED", "COMPLETED"),
    ]

    class Meta:
        db_table = "TransactionPayments"
        indexes = [
            models.Index(
                fields=["state", "payment_status", "transaction_reference"],
            )
        ]

    transaction = models.ForeignKey(
        "transactionservice.ExchangeTransactions", on_delete=models.CASCADE
    )
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    transaction_reference = models.CharField(max_length=100)
    transaction_amount = models.BigIntegerField()
    payment_status = models.CharField(
        choices=PAYMENT_STATUS, default="IN_ESCROW", max_length=50
    )
    payment_gateway = models.CharField(max_length=50)
    payment_meta = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    gateway_response = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    inflow_escrow_at = models.DateTimeField(null=True, default=None)
    reversed_at = models.DateTimeField(null=True, default=None)
    completed_at = models.DateTimeField(null=True, default=None)

    def __str__(self):
        return f"TransactionPayments>>{self.id}:Trans>>{self.transaction_id}"

    def __repr__(self):
        return f"TransactionPayments>>{self.id}:Trans>>{self.transaction_id}"

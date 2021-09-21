from rest_framework import viewsets
from rest_framework.authentication import get_authorization_header
from rest_framework.decorators import action
from utils.helpers import ResponseManager, VDFAuth

from paymentservice.serializers import (
    BankAccountLookupSerializer,
    FinalizeCardSerializer,
    FinalizeEscrowSerializer,
    InitateEscrowSerializer,
    InitiateCardSerializer,
    RevertEscrowSerializer,
)


class ExchangePaymentViewset(viewsets.ViewSet):
    @action(detail=False, url_path="bank-list")
    def bank_list(self, request):
        """ Retrieve Bank List """
        banks = VDFAuth.bank_list()
        return ResponseManager.handle_response(data=banks)

    @action(detail=False, methods=["post"], url_path="account-lookup")
    def bank_account_lookup(self, request):
        """ Bank Account Lookup """
        serialized_data = BankAccountLookupSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="initate-bank-payment/(?P<request_id>[a-z,A-Z,0-9]+)",
    )
    def initate_escrow_payment(self, request, *args, **kwargs):
        user_token = get_authorization_header(request).decode().split()[1]
        serialized_data = InitateEscrowSerializer(
            data={**request.data, **kwargs},
            context={"token": user_token, "user": request.user},
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="finalize-bank-payment/(?P<transaction_reference>[a-z,A-Z,0-9]+)",
    )
    def finalize_escrow_payment(self, request, *args, **kwargs):
        serialized_data = FinalizeEscrowSerializer(
            data={"transaction_ref": kwargs["transaction_reference"]},
            context={"user": request.user},
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="reverse-bank-payment/(?P<transaction_reference>[a-z,A-Z,0-9]+)",
    )
    def reverse_escrow_payment(self, request, *args, **kwargs):
        serialized_data = RevertEscrowSerializer(
            data={"transaction_ref": kwargs["transaction_reference"]},
            context={"user": request.user},
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="initate-card-payment/(?P<request_id>[a-z,A-Z,0-9]+)",
    )
    def initate_card_payment(self, request, *args, **kwargs):
        serialized_data = InitiateCardSerializer(
            data={**request.data, **kwargs}, context={"user": request.user}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="finalize-card-payment/(?P<transaction_ref>[a-z,A-Z,0-9]+)",
    )
    def finalize_card_payment(self, request, *args, **kwargs):
        serialized_data = FinalizeCardSerializer(
            data={**kwargs}, context={"user": request.user}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="reverse-card-payment/(?P<request_id>[a-z,A-Z,0-9]+)",
    )
    def reverse_card_payment(self, request, *args, **kwargs):
        return ResponseManager.handle_response(data="reverse_escrow_payment")

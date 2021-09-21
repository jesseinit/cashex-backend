from django.db.models import Q
from django.utils.timezone import now
from rest_framework import serializers
from transactionservice.models import ExchangeTransactions
from utils.helpers import (
    CacheManager,
    ChannelManager,
    OnePipeProvider,
    VDFAuth,
)
from utils.model_helpers import generate_id

from paymentservice.models import TransactionPayments


class BankAccountLookupSerializer(serializers.Serializer):
    bank_code = serializers.CharField(min_length=6, max_length=6)
    account_number = serializers.CharField(min_length=10, max_length=10)

    def validate(self, validated_data):
        bank_code = validated_data["bank_code"]
        account_number = validated_data["account_number"]
        account_info = VDFAuth.resolve_bank_account(
            bank_code=bank_code, account_no=account_number
        )
        if not account_info:
            raise serializers.ValidationError(
                {"account_number": ["Could not resolve this account details"]}
            )
        self.account_info = account_info
        return validated_data

    def to_representation(self, instance):
        instance["account_info"] = self.account_info
        return instance


class InitateEscrowSerializer(serializers.Serializer):
    transaction_pin = serializers.CharField(min_length=4, max_length=4, write_only=True)
    request_id = serializers.CharField(max_length=32)

    def validate_request_id(self, request_id):
        # Check that the user is a member of the transaction
        user = self.context["user"]
        exchange_transaction = ExchangeTransactions.objects.filter(
            Q(agent=user) | Q(customer=user),
            transaction_status="IN-PROGRESS",
            request_id=request_id,
        ).first()

        if not exchange_transaction:
            raise serializers.ValidationError(
                "This transaction is not found or no longer in-progress"
            )

        payment_instance = exchange_transaction.transactionpayments_set.exists()

        if payment_instance:
            raise serializers.ValidationError(
                "Payment already initiated, Kinly complete or reverse"
            )
        self.exchange_transaction = exchange_transaction

        return request_id

    def validate(self, validated_data):
        # Todo - Only users that logged in with their bank account can initiate escrow
        request_id = validated_data["request_id"]
        transaction_pin = validated_data["transaction_pin"]
        user = self.context["user"]
        customer_account_number = user.account_meta.get("accountNumber")
        agent_account_number = self.exchange_transaction.agent.account_meta.get(
            "accountNumber"
        )

        # Fetch Customer Account Details
        customer_account_details = VDFAuth.fetch_bank_accounts(
            account_no=customer_account_number
        )
        print("customer_account_details>>>", customer_account_details)
        # Todo - Sort through the list and check that the balance in the account can accomodate for the transaction
        user_bank_accounts = list(
            filter(
                lambda bank_account: bank_account["transactionEnabled"] is True
                and bank_account["accountNo"] == int(customer_account_number),
                customer_account_details,
            )
        )
        print("user_bank_accounts>>>", user_bank_accounts)
        customer_account_details = user_bank_accounts[0]
        print("customer_account_details>>>", customer_account_details)

        # Resolve Agents Bank Account
        agents_bank_details = VDFAuth.resolve_bank_account(
            account_no=agent_account_number
        )

        print("agents_bank_details>>>", agents_bank_details)

        transaction_total_in_kobo = (
            self.exchange_transaction.request_amount
            + self.exchange_transaction.request_fees
        )

        # Trigger the Escrow Transfer

        transaction_reference = generate_id()
        transfer_payload = {
            "from_acct": customer_account_number,
            "to_name": agents_bank_details["accountName"],
            "to_acct_id": agents_bank_details["accountId"],
            "to_acct_no": agents_bank_details["accountNumber"],
            "to_client_id": agents_bank_details["clientId"],
            "amount": transaction_total_in_kobo / 100,
            "reference": transaction_reference,
            "sender_name": user.first_name,
        }

        escrow_response = VDFAuth.initiate_transfer(**transfer_payload)
        payment_instance = TransactionPayments.objects.create(
            customer=user,
            transaction=self.exchange_transaction,
            transaction_amount=transaction_total_in_kobo,
            transaction_reference=transaction_reference,
            payment_gateway="VFD_BANK",
            payment_meta=transfer_payload,
            gateway_response=escrow_response,
            inflow_escrow_at=now(),
        )
        self.payment_instance = payment_instance
        data_payload = {
            "event": "user.payment.received",
            "context": "AGENT",
            "body": {
                "amount_in_kobo": transaction_total_in_kobo,
                "customer_name": user.first_name,
            },
        }

        # Send message to the channel
        ChannelManager.ws_publish(
            channel=f"transaction_{request_id}", payload=data_payload
        )

        # Set Users(Customer and Agent) Stage in the Transaction
        CacheManager.set_key(
            f"{request_id}:" f"{self.exchange_transaction.agent_id}:stage",
            "AWAITING_CASH_CONFIRMATION",
        )
        CacheManager.set_key(
            f"{request_id}:" f"{self.exchange_transaction.customer_id}:stage",
            "AWAITING_CASH_CONFIRMATION",
        )

        # Todo - Send a push notification to the agent
        return validated_data

    def to_representation(self, instance):
        instance["payment_instance"] = {
            "transaction_reference": self.payment_instance.transaction_reference
        }
        return instance


class FinalizeEscrowSerializer(serializers.Serializer):
    transaction_ref = serializers.CharField(max_length=32)

    def validate_transaction_ref(self, transaction_ref):
        user = self.context["user"]
        payment_instance = TransactionPayments.objects.filter(
            transaction_reference=transaction_ref,
            customer=user,
            payment_gateway="VFD_BANK",
        ).first()

        if payment_instance and payment_instance.payment_status == "COMPLETED":
            raise serializers.ValidationError("Payment has already been completed.")

        if not payment_instance or payment_instance.payment_status != "IN_ESCROW":
            raise serializers.ValidationError("Payment was not found in Escrow")

        self.payment_instance = payment_instance
        return transaction_ref

    def validate(self, validated_data):
        finalize_payload = {
            # Get this figure from the meta
            "transaction_id": self.payment_instance.gateway_response["transactionId"],
            "reference_id": self.payment_instance.gateway_response["reference"],
        }
        # Todo - Complete implementation of the method below
        VDFAuth.finalize_transfer(**finalize_payload)

        payment_instance = self.payment_instance.update(
            completed_at=now(), payment_status="COMPLETED"
        )
        transaction_instance = payment_instance.transaction.update(
            transaction_status="COMPLETED", closed_by="CUSTOMER", closed_at=now()
        )

        event_payload = {
            "event": "user.transaction.completed",
            "context": "AGENT",
            "body": {
                "transaction_id": transaction_instance.id,
                "customer_id": transaction_instance.customer_id,
                "agent_id": transaction_instance.agent_id,
            },
        }
        request_id = transaction_instance.request_id

        ChannelManager.ws_publish(
            channel=f"transaction_{request_id}", payload=event_payload
        )

        # Set Users(Customer and Agent) Stage in the Transaction
        transaction_group_name = f"transaction_{request_id}"
        CacheManager.delete_keys(
            f"{transaction_instance.agent_id}:stage",
            f"{transaction_instance.customer_id}:stage",
            f"{transaction_group_name}:customer_reached",
            f"{transaction_group_name}:agent_reached",
            f"request:{transaction_instance.request.request_id}",
        )
        self.transaction_instance = transaction_instance
        return validated_data

    def to_representation(self, instance):
        instance["transaction_id"] = self.transaction_instance.id
        return instance


class RevertEscrowSerializer(serializers.Serializer):
    transaction_ref = serializers.CharField(max_length=32)

    def validate_transaction_ref(self, transaction_ref):
        user = self.context["user"]
        payment_instance = TransactionPayments.objects.filter(
            transaction_reference=transaction_ref,
            customer=user,
            payment_gateway="VFD_BANK",
        ).first()

        if payment_instance and payment_instance.payment_status == "REVERSED":
            raise serializers.ValidationError("Payment has already been reversed.")

        if not payment_instance or payment_instance.payment_status != "IN_ESCROW":
            raise serializers.ValidationError("Payment was not found in Escrow")

        self.payment_instance = payment_instance
        return transaction_ref

    def validate(self, validated_data):
        reverse_payload = {
            "transaction_id": self.payment_instance.gateway_response["transactionId"],
            "reference_id": self.payment_instance.gateway_response["reference"],
        }
        VDFAuth.reverse_transfer(**reverse_payload)
        payment_instance = self.payment_instance.update(
            reversed_at=now(), payment_status="REVERSED"
        )
        transaction_instance = payment_instance.transaction.update(
            transaction_status="COMPLETED", closed_by="CUSTOMER", closed_at=now()
        )

        event_payload = {
            "event": "user.transaction.reversed",
            "context": "AGENT",
            "body": {
                "transaction_id": transaction_instance.id,
                "customer_id": transaction_instance.customer_id,
                "agent_id": transaction_instance.agent_id,
            },
        }
        request_id = transaction_instance.request_id

        ChannelManager.ws_publish(
            channel=f"transaction_{request_id}", payload=event_payload
        )

        transaction_group_name = f"transaction_{request_id}"
        CacheManager.delete_keys(
            f"{transaction_instance.agent_id}:stage",
            f"{transaction_instance.customer_id}:stage",
            f"{transaction_group_name}:customer_reached",
            f"{transaction_group_name}:agent_reached",
            f"request:{transaction_instance.request.request_id}",
        )
        self.transaction_instance = transaction_instance
        return validated_data

    def to_representation(self, instance):
        instance["transaction_id"] = self.transaction_instance.id
        return instance


class InitiateCardSerializer(serializers.Serializer):
    card_no = serializers.CharField()
    card_exp_month = serializers.ChoiceField(
        choices=["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
    )
    card_exp_year = serializers.CharField(min_length=2, max_length=2)
    card_cvv = serializers.CharField(min_length=3, max_length=3)
    card_pin = serializers.CharField(min_length=4, max_length=4)
    agent_bank_code = serializers.CharField(min_length=6, max_length=6)
    agent_account_no = serializers.CharField(min_length=10, max_length=10)
    request_id = serializers.CharField(max_length=32)

    def validate_request_id(self, request_id):
        # Check that the user is a member of the transaction
        user = self.context["user"]
        exchange_transaction = (
            ExchangeTransactions.objects.filter(
                Q(agent=user) | Q(customer=user),
                transaction_status="IN-PROGRESS",
                request_id=request_id,
            )
            .select_related("customer")
            .first()
        )
        if not exchange_transaction:
            raise serializers.ValidationError("This transaction is not found")
        payment_instance = exchange_transaction.transactionpayments_set.exists()
        if payment_instance:
            raise serializers.ValidationError("This transaction has been paid for.")
        self.exchange_transaction = exchange_transaction
        return request_id

    def validate(self, validated_data):
        request_id = validated_data["request_id"]
        user = self.context["user"]
        transacton_instance = self.exchange_transaction
        transaction_customer = transacton_instance.customer
        customer_details = {
            "customer_ref": transaction_customer.first_name,
            "firstname": transaction_customer.first_name,
            "surname": transaction_customer.last_name,
            "email": transaction_customer.email,
            "mobile_no": transaction_customer.mobile_number,
        }
        transaction_amount = (
            transacton_instance.request_amount + transacton_instance.request_fees
        )
        transaction_ref = generate_id()
        request_ref = transaction_ref
        format_card = f"{validated_data['card_no']};{validated_data['card_cvv']};{validated_data['card_exp_month']};{validated_data['card_exp_year']};{validated_data['card_pin']};"
        secure_card = OnePipeProvider.encrypt_card_data(format_card)
        if not secure_card:
            raise serializers.ValidationError(
                {"card_no": ["Your card details is invalid"]}
            )
        payment_payload = dict(
            request_ref=request_ref,
            txn_ref=transaction_ref,
            customer_data=customer_details,
            txn_amt=transaction_amount,
            txn_meta={},
            secured_card=secure_card,
        )
        payment_response = OnePipeProvider.perform_card_debit(**payment_payload)
        if not payment_response:
            raise serializers.ValidationError(
                {"payment_gateway": "Error occured processing your payment"}
            )

        payment_instance = TransactionPayments.objects.create(
            customer=user,
            transaction=transacton_instance,
            transaction_amount=transaction_amount,
            transaction_reference=transaction_ref,
            payment_gateway="ONEPIPE",
            payment_meta=payment_payload,
            gateway_response=payment_response,
            inflow_escrow_at=now(),
        )
        self.payment_instance = payment_instance
        data_payload = {
            "event": "user.payment.received",
            "context": "AGENT",
            "body": {
                "amount_in_kobo": transaction_amount,
                "customer_name": user.first_name,
            },
        }

        ChannelManager.ws_publish(
            channel=f"transaction_{request_id}", payload=data_payload
        )

        # Set Users(Customer and Agent) Stage in the Transaction
        CacheManager.set_key(
            f"{request_id}:" f"{self.exchange_transaction.agent_id}:stage",
            "AWAITING_CASH_CONFIRMATION",
        )
        CacheManager.set_key(
            f"{request_id}:" f"{self.exchange_transaction.customer_id}:stage",
            "AWAITING_CASH_CONFIRMATION",
        )

        return validated_data

    def to_representation(self, instance):
        return {
            "request_id": instance["request_id"],
            "payment_instance": {
                "transaction_reference": self.payment_instance.transaction_reference
            },
        }


class FinalizeCardSerializer(serializers.Serializer):
    transaction_ref = serializers.CharField(max_length=32)

    def validate_transaction_ref(self, transaction_ref):
        user = self.context["user"]
        payment_instance = TransactionPayments.objects.filter(
            transaction_reference=transaction_ref,
            customer=user,
            payment_status="IN_ESCROW",
            payment_gateway="ONEPIPE",
        ).first()
        if not payment_instance:
            raise serializers.ValidationError("Transaction is not in Escrow")
        self.payment_instance = payment_instance
        return transaction_ref

    def validate(self, validated_data):
        # Todo - Complete implementation of the method below
        payment_instance = self.payment_instance.update(
            completed_at=now(), payment_status="COMPLETED"
        )
        transaction_instance = payment_instance.transaction.update(
            transaction_status="COMPLETED", closed_by="CUSTOMER", closed_at=now()
        )

        event_payload = {
            "event": "user.transaction.completed",
            "context": "AGENT",
            "body": {
                "transaction_id": transaction_instance.id,
                "customer_id": transaction_instance.customer_id,
                "agent_id": transaction_instance.agent_id,
            },
        }
        request_id = transaction_instance.request_id
        ChannelManager.ws_publish(
            channel=f"transaction_{request_id}", payload=event_payload
        )

        # Set Users(Customer and Agent) Stage in the Transaction
        transaction_group_name = f"transaction_{request_id}"
        CacheManager.delete_key(
            f"{request_id}:" f"{transaction_instance.agent_id}:stage"
        )
        CacheManager.delete_key(
            f"{request_id}:" f"{transaction_instance.customer_id}:stage"
        )
        CacheManager.delete_key(f"{transaction_group_name}:agent_reached")
        CacheManager.delete_key(f"{transaction_group_name}:customer_reached")
        CacheManager.delete_key(
            f"request:{transaction_instance.request.request_id}"
        )  # Deletes the search result

        self.transaction_instance = transaction_instance

        # Todo - Send an sms Alert to the agents phone no
        return validated_data

    def to_representation(self, instance):
        instance["transaction_id"] = self.transaction_instance.id
        return instance

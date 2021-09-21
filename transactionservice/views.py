import json

from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from utils.helpers import CustomPaginator, ResponseManager, CacheManager

from transactionservice.models import ExchangeRequests, ExchangeTransactions
from transactionservice.serializers import (
    CancelExchangeTransactionSerializer,
    DispatchRequestSerializer,
    ExchangeRequestsSerializer,
    ExchangeTransactionSerializer,
    GetRequestFeesSerializer,
    HandleRequestNotificationSerializer,
    InitiateRequestSerializer,
    TransactionRatingSerializer,
)


class ExchangeRequestViewset(viewsets.ViewSet):
    @action(detail=False, methods=["post"], url_path="fees")
    def retrieve_request_fees(self, request):
        serialized_data = GetRequestFeesSerializer(data=request.data)
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(detail=False, methods=["post"], url_path="initiate")
    def initate_exchange_request(self, request):
        serialized_data = InitiateRequestSerializer(
            data=request.data, context={"user": request.user}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="requests-results/(?P<request_search_id>[a-z,A-Z,0-9]+)",
    )
    def request_search(self, request, *args, **kwargs):
        search_results = CacheManager.retrieve_key(
            f"request:{kwargs['request_search_id']}"
        )
        if not search_results:
            return ResponseManager.handle_response(
                error="Request search results not found", status=400
            )
        return ResponseManager.handle_response(data=json.loads(search_results))

    @action(
        detail=False,
        methods=["post"],
        url_path="(?P<request_search_id>[a-z,A-Z,0-9]+)/request",
    )
    def dispatch_request_to_agent(self, request, *args, **kwargs):
        serialized_data = DispatchRequestSerializer(
            data={**request.data, **kwargs}, context={"user": request.user}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="(?P<request_state>[all,pending,declined,accepted]+)",
    )
    def retrieve_requests(self, request, *args, **kwargs):
        """ Retrieves all request sent to the user is an Agent """
        user = request.user
        request_state = kwargs["request_state"].upper()
        requests_instance = {
            "ALL": ExchangeRequests.status.everything,
            "PENDING": ExchangeRequests.status.pending,
            "DECLINED": ExchangeRequests.status.declined,
            "ACCEPTED": ExchangeRequests.status.accepted,
        }
        requests_instance = requests_instance[request_state]().filter(agent=user)
        # Q(agent=user) | Q(customer=user))

        paginator = CustomPaginator(url_suffix=request.path)
        requests_instance = paginator.paginate_queryset(requests_instance, request)
        serialized_data = ExchangeRequestsSerializer(requests_instance, many=True)

        return paginator.get_paginated_response(
            data=serialized_data.data,
            status=200,
        )

    @action(
        detail=False, methods=["post"], url_path="(?P<request_id>[a-z,A-Z,0-9]+)/react"
    )
    def request_notification_handler(self, request, *args, **kwargs):
        """ Handles request notification reaction """
        serialized_data = HandleRequestNotificationSerializer(
            data={**request.data, **kwargs}, context={"agent": request.user}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)


class ExchangeTransactionsViewset(viewsets.ViewSet):
    @action(
        detail=False,
        methods=["get"],
        url_path="single/(?P<request_id>[a-z,A-Z,0-9]+)",
    )
    def retrieve_single_transactions(self, request, *args, **kwargs):
        user = request.user
        request_id = kwargs["request_id"]
        transaction_instance = ExchangeTransactions.objects.filter(
            Q(agent=user) | Q(customer=user), request_id=request_id
        ).first()
        if not transaction_instance:
            return ResponseManager.handle_response(
                error="Transaction not found", status=400
            )
        serialized_data = ExchangeTransactionSerializer(
            instance=transaction_instance, context={"user": user}
        )
        return ResponseManager.handle_response(data=serialized_data.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="(?P<transaction_state>([all|inprogress|cancelled|abandoned|completed]){3,10})",
    )
    def retrieve_transactions(self, request, *args, **kwargs):
        """ Retrieve All Transactions Based on State """
        user = request.user
        transaction_state = kwargs["transaction_state"].upper()
        transactions_instance = {
            "INPROGRESS": ExchangeTransactions.status.in_progress,
            "CANCELLED": ExchangeTransactions.status.cancelled,
            "ABANDONED": ExchangeTransactions.status.abandoned,
            "COMPLETED": ExchangeTransactions.status.completed,
            "ALL": ExchangeTransactions.status.everything,
        }
        transactions_instance = (
            transactions_instance[transaction_state]()
            .filter(Q(agent=user) | Q(customer=user))
            .select_related("request", "customer", "agent")
        )
        paginator = CustomPaginator(url_suffix=request.path)
        transactions_instance = paginator.paginate_queryset(
            transactions_instance, request
        )
        serialized_data = ExchangeTransactionSerializer(
            transactions_instance, many=True, context={"user": user}
        )
        return paginator.get_paginated_response(
            data=serialized_data.data,
            status=200,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="(?P<request_id>[a-z,A-Z,0-9]+)/cancel",
    )
    def cancel_transactions(self, request, *args, **kwargs):
        """ Customer or Agent Cancel Transaction """
        serialized_data = CancelExchangeTransactionSerializer(
            data={**request.data, **kwargs}, context={"user": request.user}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)


class ExchangeTransactionsRatingsViewset(viewsets.ViewSet):
    @action(
        detail=False,
        methods=["post"],
        url_path="(?P<transaction_id>[a-z,A-Z,0-9]+)",
    )
    def rate_transactions(self, request, *args, **kwargs):
        serialized_data = TransactionRatingSerializer(
            data={**request.data, **kwargs}, context={"user": request.user}
        )
        if not serialized_data.is_valid():
            return ResponseManager.handle_response(
                error=serialized_data.errors, status=400
            )
        return ResponseManager.handle_response(data=serialized_data.data)

import itertools
import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.db.models import Avg
from django.utils.timezone import datetime
from rest_framework import serializers
from userservice.models import User
from utils.constants import MAX_REQUEST_VALUE, MIN_REQUEST_VALUE
from utils.helpers import (
    CacheManager,
    UserDistanceManager,
    UsersAvailabilityManager,
    ChannelManager,
)
from utils.model_helpers import generate_id

from transactionservice.models import (
    ExchangeRequests,
    ExchangeTransactions,
    TransactionUserRatings,
)

channel_layer = get_channel_layer()


class GetRequestFeesSerializer(serializers.Serializer):
    request_amount = serializers.IntegerField(
        required=True, max_value=MAX_REQUEST_VALUE, min_value=MIN_REQUEST_VALUE
    )

    def validate_request_amount(self, request_amount):
        request_fee = None
        if request_amount <= MIN_REQUEST_VALUE:
            request_fee = 200 * 100
        if MIN_REQUEST_VALUE < request_amount <= 20000 * 100:
            request_fee = 250 * 100
        if 10000 * 100 < request_amount <= 50000 * 100:
            request_fee = 300 * 100
        self.fee = request_fee
        return request_amount

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep["fees"] = self.fee
        return rep


class GenericCoordinatesSerializer(serializers.Serializer):
    lat = serializers.FloatField(max_value=90, min_value=-90)
    lon = serializers.FloatField(max_value=180, min_value=-180)


class AgentsSerializer(serializers.ModelSerializer):
    ratings = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "ratings",
            "first_name",
            "last_name",
            "mobile_number",
            "image_url",
            "latitude",
            "longitude",
        )

    def get_ratings(self, obj):
        # Omo x100000
        user_ratings = obj.rated_user.aggregate(average=Coalesce(Avg("user_rating"), 0))
        return user_ratings["average"]


class InitiateRequestSerializer(GetRequestFeesSerializer):
    source_coordinates = GenericCoordinatesSerializer()
    destination_coordinates = GenericCoordinatesSerializer()

    def validate(self, validated_data):
        requester_id = self.context["user"].id
        destination_coordinates = validated_data["destination_coordinates"]
        online_user_ids = UsersAvailabilityManager.get_online_users_ids()
        if online_user_ids is None:
            raise serializers.ValidationError(
                {
                    "destination_coordinates": [
                        "There are no agents online around this location"
                    ]
                }
            )
        online_user_ids.remove(requester_id)

        busy_user_ids = ExchangeTransactions.objects.filter(
            transaction_status="IN-PROGRESS"
        ).values_list("customer", "agent")
        users_queryset = User.objects.filter(
            id__in=online_user_ids, account_type="Agent"
        ).exclude(id__in=list(busy_user_ids))

        agents_info = UserDistanceManager.get_all_users_eta(
            destination_coordinates["lat"],
            destination_coordinates["lon"],
            users_queryset,
        )

        if not agents_info:
            raise serializers.ValidationError(
                {
                    "destination_coordinates": [
                        "There are no agents online in this around the location"
                    ]
                }
            )

        self.agents_info = agents_info
        return validated_data

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep["agents_info"] = self.agents_info
        rep["customer_info"] = AgentsSerializer(self.context.get("user")).data
        request_id = generate_id()
        rep["request_search_id"] = request_id
        request_payload = json.dumps(dict(**rep), cls=DjangoJSONEncoder)
        CacheManager.set_key(f"request:{request_id}", request_payload, timeout=86400)
        return rep


class DispatchRequestSerializer(serializers.Serializer):
    agent_id = serializers.CharField()
    request_search_id = serializers.CharField()

    def validate_agent_id(self, agent_id):
        agent_instance = User.objects.filter(id=agent_id).first()
        requester_instance = self.context["user"]
        if agent_instance is None:
            raise serializers.ValidationError("This agent does not exist.")
        if agent_instance.id == requester_instance.id:
            raise serializers.ValidationError(
                "This agent is not allowed to process this request"
            )
        setattr(self, "agent_instance", agent_instance)
        return agent_id

    def validate_request_search_id(self, request_search_id):
        cached_request = CacheManager.retrieve_key(f"request:{request_search_id}")
        if cached_request is None:
            raise serializers.ValidationError("This request does not exist")
        setattr(self, "cached_request", json.loads(cached_request))
        return request_search_id

    def validate(self, validated_data):
        agent_id = validated_data["agent_id"]
        cached_request = self.cached_request
        agent_instance = self.agent_instance

        # Checks that the agent is in the search result of available agents
        is_agent_present = bool(
            filter(
                lambda agent_data: agent_id == agent_data["user_data"]["id"],
                cached_request["agents_info"],
            )
        )
        if not is_agent_present:
            raise serializers.ValidationError(
                {"agent_id": ["This agent is not allowed to process this request"]}
            )

        # Prevent Double Disptach
        is_already_distpached = ExchangeRequests.objects.filter(
            agent=agent_instance, request_id=cached_request["request_search_id"]
        ).exists()
        if is_already_distpached:
            raise serializers.ValidationError(
                {"agent_id": ["This agent has already been informed"]}
            )

        return validated_data

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        customer = self.context["user"]
        agent = self.agent_instance
        created_request = ExchangeRequests.objects.create(
            agent=agent,
            customer=customer,
            request_id=self.cached_request["request_search_id"],
            request_meta=self.cached_request,
        )
        rep["request_id"] = created_request.id

        # Send a Push Notification to the Agent
        request_amount = "{:,.2f}".format(self.cached_request["request_amount"] / 100)
        agent.send_push_notification(
            title="New Cash Exchange Request",
            body=f"{customer.first_name} is requesting a cash excahange of N{request_amount}",
            context={"request_id": created_request.id, "type": "NEW_REQUEST_INVITE"},
        )

        return rep


class ExchangeRequestsSerializer(serializers.ModelSerializer):
    request_meta = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeRequests
        fields = "__all__"

    def get_request_meta(self, instance):
        cached_request = CacheManager.retrieve_key(f"request:{instance.request_id}")
        if cached_request:
            cached_request = json.loads(cached_request)
        request_meta = instance.request_meta or cached_request
        if not request_meta:
            return None
        request_meta = dict(
            request_id=instance.id,
            request_amount=instance.request_meta["request_amount"],
            fees=instance.request_meta["fees"],
            my_data=instance.request_meta["agents_info"][0]["user_data"],
            eta_detail=instance.request_meta["agents_info"][0]["distance_details"],
            requested_at=instance.request_meta["agents_info"][0]["requested_at"],
            destination_street_name=instance.request_meta["agents_info"][0][
                "destination_street_name"
            ],
            customer_info=instance.request_meta["customer_info"],
            destination_coordinates=instance.request_meta["destination_coordinates"],
        )
        return request_meta


class HandleRequestNotificationSerializer(serializers.Serializer):
    reaction = serializers.ChoiceField(choices=["ACCEPTED", "DECLINED"])
    current_coordinates = GenericCoordinatesSerializer()
    request_id = serializers.CharField()

    def validate(self, validated_data):
        request_id = validated_data["request_id"]
        reaction = validated_data["reaction"]
        agent_instance = self.context["agent"]
        request_instance = ExchangeRequests.objects.filter(
            id=request_id, agent=agent_instance, request_status="PENDING"
        ).first()
        if request_instance is None:
            raise serializers.ValidationError(
                {
                    "request_id": [
                        "There is no pending request for this user with this details"
                    ]
                }
            )
        if reaction == "DECLINED":
            event_payload = {
                "event": "user.request.declined",
                "context": "CUSTOMER",
                "body": {},
            }
            ChannelManager.ws_publish(
                channel=f"transaction_{request_id}", payload=event_payload
            )
            request_instance.update(request_status=reaction)
            # Todo - Send Notification to the requester{request_instance.user}
            return validated_data
        # Todo - Check to see that customer isn't in another inprogress  before agent accets

        is_customer_busy = ExchangeTransactions.objects.filter(
            transaction_status="IN-PROGRESS", customer=request_instance.customer
        ).exists()

        if is_customer_busy is True:
            raise serializers.ValidationError(
                {
                    "customer_id": [
                        "Oops the customer is in another transaction. Try again later."
                    ]
                }
            )

        # Accepts the request and create a transaction
        request_instance = request_instance.update(request_status=reaction)
        destination_coordinates = request_instance.request_meta[
            "destination_coordinates"
        ]

        # Todo - Create Transaction and Start Process
        ExchangeTransactions.objects.create(
            transaction_status="IN-PROGRESS",
            request=request_instance,
            request_amount=request_instance.request_meta["request_amount"],
            request_fees=request_instance.request_meta["fees"],
            customer=request_instance.customer,
            agent=agent_instance,
            dest_latitude=destination_coordinates["lat"],
            dest_longitude=destination_coordinates["lon"],
        )
        current_coordinates = validated_data["current_coordinates"]
        computed_eta_data = UserDistanceManager.get_user_eta(
            current_coordinates["lat"],
            current_coordinates["lon"],
            destination_coordinates["lat"],
            destination_coordinates["lon"],
        )
        data_payload = {
            "event": "user.request.accepted",
            "context": "CUSTOMER",
            "body": {
                "eta_data": computed_eta_data,
                "current_lat": current_coordinates["lat"],
                "current_lon": current_coordinates["lon"],
            },
        }

        ChannelManager.ws_publish(
            channel=f"transaction_{request_id}", payload=data_payload
        )

        return validated_data


class ExchangeTransactionSerializer(serializers.ModelSerializer):
    customer = AgentsSerializer()
    agent = AgentsSerializer()
    transaction_stage = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeTransactions
        fields = "__all__"
        # depth = 1

    def get_transaction_stage(self, obj):
        user = self.context["user"]
        return CacheManager.retrieve_key(f"{obj.request_id}:" f"{user.id}:stage")


class CancelExchangeTransactionSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField()
    request_id = serializers.CharField()

    def validate_request_id(self, request_id):
        # Todo - User shouldn't be able to cancel a transacton when cash is in ESCROW
        user = self.context["user"]
        transaction_instance = ExchangeTransactions.objects.filter(
            Q(agent=user) | Q(customer=user),
            transaction_status="IN-PROGRESS",
            request_id=request_id,
        ).first()
        if not transaction_instance:
            raise serializers.ValidationError("Exchange transaction not found")
        setattr(self, "transaction_instance", transaction_instance)
        return request_id

    def validate(self, validated_data):
        cancellation_reason = validated_data["cancellation_reason"]
        request_id = validated_data["request_id"]
        user = self.context["user"]
        transaction_instance = self.transaction_instance
        close_initiator = (
            "AGENT" if transaction_instance.agent_id == user.id else "CUSTOMER"
        )
        transaction_instance.update(
            cancellation_reason=cancellation_reason,
            closed_at=datetime.now(),
            closed_by=close_initiator,
            transaction_status="CANCELLED",
        )
        data_payload = {
            "event": "user.transaction.cancelled",
            "context": "AGENT" if close_initiator == "CUSTOMER" else "CUSTOMER",
            "body": {},
        }
        ChannelManager.ws_publish(
            channel=f"transaction_{request_id}", payload=data_payload
        )
        return validated_data


class TransactionRatingSerializer(serializers.Serializer):
    transaction_id = serializers.CharField()
    user_rating = serializers.IntegerField(min_value=1, max_value=5)

    def validate_transaction_id(self, transaction_id):
        user = self.context["user"]
        # Todo - Check that if the transaction has been completed
        transaction_instance = ExchangeTransactions.objects.filter(
            Q(agent=user) | Q(customer=user),
            transaction_status="COMPLETED",
            id=transaction_id,
        ).first()
        if not transaction_instance:
            raise serializers.ValidationError(
                "Rating Failed. Transaction not completed or found"
            )
        # Todo - Check that if user has left a rating before
        already_rated = TransactionUserRatings.objects.filter(
            transaction_id=transaction_id, rating_user=user
        ).exists()
        if already_rated is True:
            raise serializers.ValidationError("You've rated this transaction already.")
        self.transaction_instance = transaction_instance
        return transaction_id

    def validate(self, validated_data):
        rating_user = self.context["user"]
        user_rating = validated_data["user_rating"]
        transaction_instance = self.transaction_instance
        rated_user = (
            transaction_instance.customer
            if rating_user.id == transaction_instance.agent_id
            else transaction_instance.agent
        )
        TransactionUserRatings.objects.create(
            user_rating=user_rating,
            transaction=transaction_instance,
            rating_user=rating_user,
            rated_user=rated_user,
        )
        return validated_data

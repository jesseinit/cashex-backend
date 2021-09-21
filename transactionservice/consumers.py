import json
from asgiref.sync import async_to_sync, sync_to_async
from channels.generic.websocket import WebsocketConsumer, AsyncJsonWebsocketConsumer
from django.db.models import Q
from django.utils.timezone import datetime
from sentry_sdk import capture_exception
from utils.helpers import CacheManager, UserDistanceManager

from transactionservice.models import ExchangeRequests, ExchangeTransactions
from channels.db import database_sync_to_async


class TransactionConsumer(AsyncJsonWebsocketConsumer):

    has_agent_arrived = None
    has_customer_arrived = None

    async def connect(self):
        self.request_id = self.scope["url_route"]["kwargs"]["request_id"]
        self.transaction_group_name = f"transaction_{self.request_id}"
        self.user = self.scope["user"]
        is_user_authenticated = self.user.is_authenticated
        await self.channel_layer.group_add(
            self.transaction_group_name, self.channel_name
        )

        await self.accept()

        if not is_user_authenticated:
            await self.send_json({"message": "You're not authenticated"})
            return await self.close(1000)

        is_valid_txn_member = await self._is_transaction_member(
            self.request_id, self.scope["user"]
        )
        if not is_valid_txn_member:
            await self.send_json(
                {"message": "You are not a participant in this transaction"}
            )
            return await self.close(1000)

        await self.send_json(
            {"message": f"Connected to Request with ID->>{self.request_id}"}
        )

    async def disconnect(self, close_code):
        """ Leave transaction group """
        await self.channel_layer.group_discard(
            self.transaction_group_name, self.channel_name
        )

    async def receive_json(self, event_dict):
        """ This function is called when client sends data to the server """
        try:
            event_name = event_dict.get("event")
            print("INCOMING_DATA>>>>", event_dict)
            channel_data_params = {"type": None, "event_data": event_dict}

            # Handles Location Events
            if event_name == "user.location.updated":
                computed_eta_data = await self._proprocess_eta_data(event_dict)
                event_dict["computed_eta_data"] = computed_eta_data
                channel_data_params["type"] = "handle_user_eta"
                channel_data_params["event_data"] = event_dict

            # Handles Identity Events
            if event_name == "user.identity.customer:confirmed":
                has_customer_arrived = CacheManager.retrieve_key(
                    f"{self.transaction_group_name}:customer_reached"
                )
                if not has_customer_arrived:
                    return await self.send_json(
                        {"message": "Customer has not reached the destination"}
                    )
                channel_data_params["type"] = "user_identity_update"

            if event_name == "user.identity.agent:confirmed":
                has_agent_arrived = CacheManager.retrieve_key(
                    f"{self.transaction_group_name}:agent_reached"
                )
                if not has_agent_arrived:
                    return await self.send_json(
                        {"message": "Agent has not reached the destination"}
                    )
                channel_data_params["type"] = "user_identity_update"

            if event_name in [
                "user.identity.customer:denied",
                "user.identity.agent:denied",
            ]:
                channel_data_params["type"] = "user_identity_update"

            return await self.channel_layer.group_send(
                self.transaction_group_name, channel_data_params
            )

        except Exception as e:
            capture_exception(e)

    async def server_event_trigger(self, event):
        """ Handles general event triggering from server """
        event_data = event["event_data"]
        await self.send_json(event_data)

    async def handle_user_eta(self, event):
        try:
            event_data = event["event_data"]
            data_payload = event_data

            has_agent_arrived = CacheManager.retrieve_key(
                f"{self.transaction_group_name}:agent_reached"
            )

            has_customer_arrived = CacheManager.retrieve_key(
                f"{self.transaction_group_name}:customer_reached"
            )

            if has_agent_arrived and has_customer_arrived:
                data_payload["event"] = "user.location.both_reached"
                return await self.send_json(data_payload)

            current_coordinates = event_data.get("body")
            eta_data = event_data.get("computed_eta_data")
            context = event_data.get("context")
            data_payload = {
                "event": "user.location.updated",
                "context": context,
                "body": {
                    "eta_data": eta_data,
                    "current_lat": current_coordinates["lat"],
                    "current_lon": current_coordinates["lon"],
                },
            }

            if has_agent_arrived and context == "CUSTOMER":
                data_payload["event"] = "user.location.reached"
                return await self.send_json(data_payload)

            if has_customer_arrived and context == "AGENT":
                data_payload["event"] = "user.location.reached"
                return await self.send_json(data_payload)

            if eta_data and eta_data["distance_value"] <= 5:
                if context == "CUSTOMER":
                    data_payload["event"] = "user.location.reached"
                    CacheManager.set_key(
                        f"{self.request_id}:" f"{self.user.id}:stage",
                        "AWAITING_IDENTITY_CONFIRMATION",
                    )
                    CacheManager.set_key(
                        f"{self.transaction_group_name}:agent_reached", True
                    )
                    has_agent_arrived = True
                elif context == "AGENT":
                    CacheManager.set_key(
                        f"{self.request_id}:" f"{self.user.id}:stage",
                        "AWAITING_IDENTITY_CONFIRMATION",
                    )
                    CacheManager.set_key(
                        f"{self.transaction_group_name}:customer_reached", True
                    )
                    data_payload["event"] = "user.location.reached"
                    has_customer_arrived = True

                if has_agent_arrived and has_customer_arrived:
                    data_payload["event"] = "user.location.both_reached"
                    return await self.send_json(data_payload)

            await self.send_json(data_payload)
        except Exception as e:
            capture_exception(e)

    async def user_identity_update(self, event):
        """ Handles User Identity Updates """
        data_payload = {}

        is_agent_confirmed = CacheManager.retrieve_key(
            f"{self.transaction_group_name}:agent:identity"
        )

        is_customer_confirmed = CacheManager.retrieve_key(
            f"{self.transaction_group_name}:customer:identity"
        )

        if all([is_agent_confirmed, is_customer_confirmed]):
            data_payload["event"] = "user.identity.both_confirmed"
            return await self.send_json(data_payload)

        event_data = event["event_data"]
        event_name = event_data["event"]
        event_context = event_data.get("context")

        if event_name == "user.identity.agent:confirmed":
            CacheManager.set_key(
                f"{self.request_id}:" f"{self.user.id}:stage",
                "AWAITING_PAYMENT_INITIATION",
            )
            CacheManager.set_key(f"{self.transaction_group_name}:agent:identity", True)
            is_agent_confirmed = True

        if event_name == "user.identity.customer:confirmed":
            CacheManager.set_key(
                f"{self.request_id}:" f"{self.user.id}:stage",
                "AWAITING_PAYMENT_INITIATION",
            )
            CacheManager.set_key(
                f"{self.transaction_group_name}:customer:identity", True
            )
            is_customer_confirmed = True

        if all([is_agent_confirmed, is_customer_confirmed]):
            CacheManager.set_key(
                f"{self.request_id}:" f"{self.user.id}:stage",
                "AWAITING_PAYMENT_INITIATION",
            )
            data_payload["event"] = "user.identity.both_confirmed"
            return await self.send_json(data_payload)

        if event_name in [
            "user.identity.customer:denied",
            "user.identity.agent:denied",
        ]:
            data_payload = {
                "event": "user.transaction.cancelled",
            }
            await self.send_json(data_payload)
            await self._cancel_transaction(event_context)
            return await self.close(1000)

        await self.send_json(event_data)

    async def _proprocess_eta_data(self, event_data):
        # Todo - Add condition to prevent redundant calls when user has reached
        destination_coordinates = CacheManager.retrieve_key(
            f"{self.request_id}:destination_coordinates"
        )
        current_coordinates = event_data.get("body")
        context = event_data.get("context")

        has_agent_arrived = CacheManager.retrieve_key(
            f"{self.transaction_group_name}:agent_reached"
        )

        has_customer_arrived = CacheManager.retrieve_key(
            f"{self.transaction_group_name}:customer_reached"
        )

        if has_agent_arrived and context == "CUSTOMER":
            return None

        if has_customer_arrived and context == "AGENT":
            return None

        # Call me only when the user triggering this hasn't arrived
        computed_eta_data = await sync_to_async(UserDistanceManager.get_user_eta)(
            current_coordinates.get("lat"),
            current_coordinates.get("lon"),
            destination_coordinates.get("lat"),
            destination_coordinates.get("lon"),
        )

        return computed_eta_data

    @database_sync_to_async
    def _is_transaction_member(self, request_id, user_instance):
        """ Method to check that a user can participate in a transaction """
        allow_entry = False

        accepted_request = ExchangeRequests.objects.filter(
            Q(customer=user_instance) | Q(agent=user_instance), id=request_id
        ).first()
        if accepted_request:
            CacheManager.set_key(
                f"{request_id}:destination_coordinates",
                accepted_request.request_meta["destination_coordinates"],
                timeout=86400,
            )
            allow_entry = True

        is_exchange_cancelled = ExchangeTransactions.objects.filter(
            request_id=request_id,
            transaction_status__in=["CANCELLED", "ABANDONED"],
        ).exists()

        if is_exchange_cancelled:
            CacheManager.delete_key(f"{request_id}:destination_coordinates")
            allow_entry = False

        return allow_entry

    @database_sync_to_async
    def _cancel_transaction(self, event_context):
        transaction_instance = ExchangeTransactions.objects.filter(
            transaction_status="IN-PROGRESS", request_id=self.request_id
        ).first()
        if transaction_instance:
            close_initiator = "AGENT" if event_context == "CUSTOMER" else "CUSTOMER"
            transaction_instance.update(
                cancellation_reason=f"{close_initiator} cancelled. Identity Mismatch",
                closed_at=datetime.now(),
                closed_by=close_initiator,
                transaction_status="CANCELLED",
            )
        return transaction_instance

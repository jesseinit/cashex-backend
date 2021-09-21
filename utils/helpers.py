import hashlib
import base64
from datetime import timedelta
from string import Template
from typing import List, Union, Dict

import jwt
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.timezone import datetime
from rest_framework.pagination import PageNumberPagination

from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param
from sentry_sdk import capture_exception

from utils.constants import INITATE_TRANSFER_HEADERS, FINALIZE_REVERSE_TRANSFER_HEADERS
from utils.exceptions import UnavailableResourceException

channel_layer = get_channel_layer()


class ResponseManager:
    @staticmethod
    def handle_response(message=None, data=None, error=None, status=200) -> Response:
        if error:
            return Response({"message": message, "error": error}, status=status)
        return Response({"message": message, "data": data}, status=status)

    @staticmethod
    def handle_template_response(context_data, template_name, status=200) -> Response:
        return Response(context_data, template_name=template_name, status=status)


class CacheManager:
    @classmethod
    def set_key(cls, key, data, timeout=None):
        cache.set(key, data, timeout=timeout)

    @classmethod
    def retrieve_key(cls, key):
        return cache.get(key)

    @classmethod
    def retrieve_pattern(cls, pattern):
        return cache.keys(pattern)

    @classmethod
    def retrieve_pattern_values(cls, pattern):
        return [cls.retrieve_key(key) for key in cls.retrieve_pattern(pattern)]

    @classmethod
    def delete_key(cls, key: str = None):
        return cache.delete(key)

    @classmethod
    def delete_keys(cls, *keys):
        return [cls.delete_key(key) for key in keys]


class UsersAvailabilityManager:
    """ Utility manager class for tracking user online status """

    # Sets how long(in seconds) a user last seen data should be cached
    LAST_SEEN_CACHE_TTL = 4000
    # Sets the time difference (in seconds) since a user was online 😁
    ELAPSE_LAST_SEEN_TTL = 5000

    @classmethod
    def set_user_last_seen(cls, user):
        last_seen_data = {"user_id": user.id, "time": datetime.now()}
        CacheManager.set_key(
            key=f"last_seen:{user.id}",
            data=last_seen_data,
            timeout=cls.LAST_SEEN_CACHE_TTL,
        )

    # Retrieve online users
    @classmethod
    def get_online_users_ids(cls):
        user_cache_keys = CacheManager.retrieve_pattern("last_seen:*")
        if user_cache_keys is None:
            return []
        users_data = [CacheManager.retrieve_key(key) for key in user_cache_keys]
        time_in_past = datetime.now() - timedelta(seconds=cls.ELAPSE_LAST_SEEN_TTL)
        return [user["user_id"] for user in users_data if user["time"] > time_in_past]


class TokenManager:
    @classmethod
    def sign_token(cls, payload: dict = {}, exipire_at=None) -> str:
        token = jwt.encode(
            {
                **payload,
                "iat": settings.JWT_SETTINGS["ISS_AT"](),
                "exp": exipire_at or settings.JWT_SETTINGS["EXP_AT"](),
            },
            settings.SECRET_KEY,
        )
        return token

    @classmethod
    def parse_token(cls, token):
        return jwt.decode(token, options={"verify_signature": False})

    @classmethod
    def decode_token(cls, token):
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


class ProjectOSRMProvider:
    BASE_URL = Template(
        # "http://localhost:5022/route/v1/driving/$user_long,$user_lat;$dest_long,$dest_lat")
        # "https://router.project-osrm.org/route/v1/driving/$user_long,$user_lat;$dest_long,$dest_lat")
        f"{settings.OSRM_BASE_URL}/route/v1/driving/$user_long,$user_lat;$dest_long,$dest_lat"
    )

    @classmethod
    def get_route_data(cls, **kwargs):
        try:
            print("Calling Matrix with>>>", kwargs)
            distance_response = requests.get(
                cls.BASE_URL.substitute(**kwargs), timeout=2
            )
            if not distance_response.ok or distance_response is None:
                return None
            return distance_response.json()
        except Exception as e:
            capture_exception(e)
            return None


class UserDistanceManager:
    SEARCH_RADIUS_IN_KM = 100000  # Distance in meters
    DISTANCE_MATRIX_PROVIDER = ProjectOSRMProvider
    # Compute user distance information

    @classmethod
    def get_user_eta_profile(cls, user, dest_lat: float, dest_long: float):
        from userservice.serializers import UserProfileSerializer

        distance_response = cls.DISTANCE_MATRIX_PROVIDER.get_route_data(
            user_long=user.longitude,
            user_lat=user.latitude,
            dest_long=dest_long,
            dest_lat=dest_lat,
        )

        if distance_response is None:
            return None

        user_distance = distance_response["routes"][0]["distance"]
        if user_distance > cls.SEARCH_RADIUS_IN_KM:
            return None

        user_data = UserProfileSerializer(
            user,
            fields=(
                "id",
                "email",
                "transaction_summary",
                "first_name",
                "address",
                "last_name",
                "mobile_number",
                "image_url",
                "latitude",
                "longitude",
            ),
        ).data
        txns_summary = user_data.pop("transaction_summary")
        dest_addr = distance_response["waypoints"][1]["name"]
        user_duration = int(distance_response["routes"][0]["duration"])
        user_eta_data = {
            "user_data": {
                **user_data,
                "agent_rating": txns_summary["avg_ratings"],
                "success_trans_count": txns_summary["total_transactions"],
            },
            "destination_street_name": dest_addr or "Unnamed Street",
            "distance_details": {
                "distance": {
                    "text": cls.distance_converter(user_distance),
                    "value": int(user_distance),
                },
                "duration": {
                    "text": cls.duration_converter(user_duration),
                    "value": user_duration,
                },
            },
            "requested_at": datetime.now(),
        }
        return user_eta_data

    @classmethod
    def get_all_users_eta(
        cls, dest_lat: float, dest_long: float, user_queryset: list
    ) -> Union[list, None]:
        """ Fetches all active users within the radius the set destination """
        nearby_agents = []
        for user in user_queryset:
            user_data = UserDistanceManager.get_user_eta_profile(
                user, dest_lat, dest_long
            )
            if user_data:
                nearby_agents.append(user_data)
        return nearby_agents

    @classmethod
    def get_user_eta(cls, user_lat, user_long, dest_lat, dest_long):

        # return dict(
        #     distance_text="3m",
        #     distance_value=3,
        #     duration_text="1 min",
        #     duration_value=45,
        # )

        eta_response = cls.DISTANCE_MATRIX_PROVIDER.get_route_data(
            user_long=user_long,
            user_lat=user_lat,
            dest_long=dest_long,
            dest_lat=dest_lat,
        )

        if not eta_response:
            return None

        distance_value = int(eta_response["routes"][0]["distance"])
        duration_value = int(eta_response["routes"][0]["duration"])

        return dict(
            distance_text=cls.distance_converter(distance_value),
            distance_value=distance_value,
            duration_text=cls.duration_converter(duration_value),
            duration_value=duration_value,
        )

    @classmethod
    def distance_converter(cls, distance_in_meters):
        return (
            f"{distance_in_meters/1000:.2f} km"
            if distance_in_meters > 1000
            else f"{distance_in_meters} m"
        )

    @classmethod
    def duration_converter(cls, duration_in_seconds):
        return (
            f"{int(duration_in_seconds/60)} min"
            if duration_in_seconds > 60
            else "1 min"
        )


class VDFAuth:
    VFD_BASE_URL = settings.VFD_BASE_URL
    VFD_BEARER_TOKEN = settings.VFD_BEARER_TOKEN
    VFD_SECRET_KEY = settings.VFD_SECRET_KEY

    @classmethod
    def encode_secure_header(cls, value=None) -> str:
        """ Generate encoded header values """
        md5_hash = hashlib.sha512(f"{value}&{cls.VFD_SECRET_KEY}".encode())
        return base64.b64encode(md5_hash.digest()).decode()

    @classmethod
    def validate_bvn_or_bank(cls, entity_type=None, entity_value=None) -> Dict:
        """
        Fetches a BVN or Bank Account Details

        Parameters:
            entity_type (str): A string thats either `bvn` or `account`
            entity_value (str): The entity value

        Returns:
            enquiry_response (dict): Account details of the entity

        """
        try:
            if not settings.IS_PROD_ENV:
                return {
                    "accountNumber": "1001549500",
                    "accountName": "Babatunde Moses Daniel",
                    "firstname": "Babatunde",
                    "middlename": "Moses",
                    "lastname": "Daniel",
                    "dob": "05-Oct-1988",
                    "email": "tunesco29@yahoo.com",
                    "phone": "09087284952_144",
                }

            if entity_type == "bvn":
                url_params = f"bvn={entity_value}"
            else:
                url_params = f"accountNo={entity_value}"
            response = requests.get(
                url=cls.VFD_BASE_URL + f"/account/verify?{url_params}",
                headers={
                    "Authorization": f"Bearer {cls.VFD_BEARER_TOKEN}",
                    "X-MACDATA": cls.encode_secure_header(value=entity_value),
                },
                timeout=5,
            )
            if not response.ok:
                raise UnavailableResourceException(
                    detail={"error": "The Enquiry service is down. Try again later."}
                )
            return response.json()["data"]
        except Exception as e:
            capture_exception(e)
            raise UnavailableResourceException(
                detail={"error": "The Enquiry service is down. Try again later."}
            )

    @classmethod
    def bank_list(cls):
        try:
            cached_bank_list = CacheManager.retrieve_key("bank_list")
            if cached_bank_list:
                return cached_bank_list
            response = requests.get(
                url=cls.VFD_BASE_URL + "/banks?limit=999&offset=0",
                headers=dict(
                    Authorization=f"Bearer {cls.VFD_BEARER_TOKEN}",
                    Accept="application/json",
                ),
                timeout=20,
            )
            if not response.ok:
                raise UnavailableResourceException(
                    detail={
                        "error": "The bank listing service is down. Try again later."
                    }
                )
            response = response.json()
            CacheManager.set_key("bank_list", response["banks"]["bank"], timeout=86400)
            return response["banks"]["bank"]
        except Exception as e:
            capture_exception(e)
            raise UnavailableResourceException(
                detail={"error": "The bank listing service is down. Try again later."}
            )

    @classmethod
    def resolve_bank_account(cls, bank_code: str = "999999", account_no=None):
        # Todo - Remove this when moving to prod
        if settings.IS_PROD_ENV is False:
            return {
                "accountNumber": "1001549500",
                "accountName": "Babatunde Moses Daniel",
                "clientId": "138421",
                "accountId": "154950",
            }
        try:
            cached_response = CacheManager.retrieve_key(
                f"user:bank:{bank_code}:{account_no}"
            )
            if cached_response:
                return cached_response
            entity_value = ""
            response = requests.post(
                url=cls.VFD_BASE_URL + "/accounts/lookup",
                json={"bank": bank_code, "account": account_no},
                headers={
                    "Authorization": f"Bearer {cls.VFD_BEARER_TOKEN}",
                    "X-MACDATA": cls.encode_secure_header(value=entity_value),
                },
                timeout=20,
            )
            if not response.ok:
                raise UnavailableResourceException(
                    detail={"error": "Could not resolve bank account. Try again later."}
                )
            response_data = response.json()
            CacheManager.set_key(
                f"user:bank:{bank_code}:{account_no}",
                response_data["data"],
                timeout=86400,
            )
            return response_data["data"]
        except Exception as e:
            capture_exception(e)
            raise UnavailableResourceException(
                detail={"error": "Could not resolve bank account. Try again later."}
            )

    @classmethod
    def fetch_bank_accounts(cls, account_no=None):
        """ Fetch user bank accounts """
        if settings.IS_PROD_ENV is False:
            return [
                {
                    "id": 154950,
                    "accountNo": 1001549500,
                    "accountType": "Savings Account",
                    "accountBalance": 4932471.780000,
                    "productId": 33,
                    "productName": "Universal Savings Account",
                    "status": "Active",
                    "currency": "NGN",
                    "nickname": "My savings test new",
                    "transactionEnabled": True,
                }
            ]
        try:
            response = requests.get(
                url=cls.VFD_BASE_URL + f"/client-accounts/{account_no}",
                headers={
                    "Authorization": f"Bearer {cls.VFD_BEARER_TOKEN}",
                    "X-MACDATA": cls.encode_secure_header(value=account_no),
                },
                timeout=5,
            )
            if not response.ok:
                raise UnavailableResourceException(
                    detail={"error": "Could not fetch bank account. Try again later."}
                )
            response = response.json()
            return response["accounts"]["account"]
        except Exception as e:
            capture_exception(e)
            raise UnavailableResourceException(
                detail={"error": "Could not fetch bank account. Try again later."}
            )

    @classmethod
    def initiate_transfer(
        cls,
        from_acct=None,
        to_bank_code="999999",
        to_name=None,
        to_acct_id=None,
        to_acct_no=None,
        to_client_id=None,
        amount=None,
        reference=None,
        sender_name=None,
    ):
        if settings.IS_PROD_ENV is False:
            return {"reference": reference, "transactionId": "2413785"}
        try:
            trf_payload = {
                "from": {"accountNo": from_acct},
                "to": {
                    "bank": to_bank_code,
                    "name": to_name,
                    "accountId": to_acct_id,
                    "accountNo": to_acct_no,
                    "clientId": to_client_id,
                },
                "narration": {
                    "description": f"cashx//transfer to {to_name.capitalize()}",
                    "beneficiary": f"cashx//transfer from {sender_name.capitalize()}",
                },
                "transaction": {"amount": amount, "reference": reference},
            }

            transfer_headers = INITATE_TRANSFER_HEADERS.substitute(
                from_acct_no=trf_payload["from"]["accountNo"],
                narration_beneficiary=trf_payload["narration"]["beneficiary"],
                narration_description=trf_payload["narration"]["description"],
                to_acct_id=trf_payload["to"]["accountId"],
                to_acct_no=trf_payload["to"]["accountNo"],
                to_client_id=trf_payload["to"]["clientId"],
                to_client_name=trf_payload["to"]["name"],
                trans_amt=trf_payload["transaction"]["amount"],
                trans_ref=trf_payload["transaction"]["reference"],
            )
            headers = {
                "Authorization": f"Bearer {cls.VFD_BEARER_TOKEN}",
                "X-MACDATA": cls.encode_secure_header(value=transfer_headers),
            }

            response = requests.post(
                url=f"{cls.VFD_BASE_URL}/transfer",
                json=trf_payload,
                headers=headers,
                timeout=5,
            )
            if not response.ok:
                raise UnavailableResourceException(
                    detail={"error": "The Enquiry service is down. Try again later."}
                )
            return response.json()["data"]
        except Exception as e:
            capture_exception(e)
            raise UnavailableResourceException(
                detail={"error": "The Enquiry service is down. Try again later."}
            )

    @classmethod
    def finalize_transfer(cls, transaction_id=None, reference_id=None):
        """ Method to transfer funds from Escrow to Agent Account"""
        # Todo - Implement Finalize Call
        # return {"message": "Transfer successfully posted", "code": "57739"}
        try:
            if not settings.IS_PROD_ENV:
                return {"reference": reference_id, "transactionId": reference_id}

            transfer_headers = FINALIZE_REVERSE_TRANSFER_HEADERS(
                transaction_id=transaction_id, reference=reference_id
            )

            headers = {
                "Authorization": f"Bearer {cls.VFD_BEARER_TOKEN}",
                "X-MACDATA": cls.encode_secure_header(value=transfer_headers),
            }

            response = requests.post(
                url=f"{cls.VFD_BASE_URL}/transactions/finalize",
                json={"transactionId": transaction_id, "reference": reference_id},
                headers=headers,
                timeout=5,
            )
            if not response.ok:
                raise UnavailableResourceException(
                    detail={
                        "error": "Could not complete this transaction. Try again later."
                    }
                )
            return response.json()["data"]
        except Exception as e:
            capture_exception(e)
            raise UnavailableResourceException(
                detail={
                    "error": "Could not complete this transaction. Try again later."
                }
            )

    @classmethod
    def reverse_transfer(cls, transaction_id=None, reference_id=None):
        try:
            if not settings.IS_PROD_ENV:
                return {"reference": reference_id, "transactionId": reference_id}

            transfer_headers = FINALIZE_REVERSE_TRANSFER_HEADERS(
                transaction_id=transaction_id, reference=reference_id
            )

            headers = {
                "Authorization": f"Bearer {cls.VFD_BEARER_TOKEN}",
                "X-MACDATA": cls.encode_secure_header(value=transfer_headers),
            }

            response = requests.post(
                url=f"{cls.VFD_BASE_URL}/transactions/reverse",
                json={"transactionId": transaction_id, "reference": reference_id},
                headers=headers,
                timeout=5,
            )
            if not response.ok:
                raise UnavailableResourceException(
                    detail={
                        "error": "Could not reverse this transaction. Try again later."
                    }
                )
            return response.json()["data"]
        except Exception as e:
            capture_exception(e)
            raise UnavailableResourceException(
                detail={"error": "Could not reverse this transaction. Try again later."}
            )


class CustomPaginator(PageNumberPagination):
    """ Custom page pagination class """

    page_size = 7
    page_size_query_param = "page_size"

    def __init__(self, **kwargs):
        if kwargs.get("url_suffix"):
            self.url_suffix = kwargs["url_suffix"]
        else:
            self.url_suffix = ""

    def paginate_queryset(self, queryset, request, view=None):
        from django.core.paginator import InvalidPage

        self.host = settings.BACKEND_URL
        self.request = request
        page_size = self.get_page_size(self.request)
        if not page_size:
            return None

        paginator = self.django_paginator_class(queryset, page_size)
        page_number = request.query_params.get(self.page_query_param, 1)
        if page_number in self.last_page_strings:
            page_number = paginator.num_pages

        try:
            self.page = paginator.page(page_number)
        except InvalidPage:
            from rest_framework.exceptions import NotFound

            raise NotFound(dict(error="The requested page does not exists", status=404))

        if paginator.num_pages > 1 and self.template is not None:
            self.display_page_controls = True

        self.request = request
        return list(self.page)

    def get_paginated_response(self, data, query_params=None, **kwargs):
        status = kwargs.get("status", 200)
        return Response(
            {
                **kwargs,
                "total_pages": self.page.paginator.num_pages,
                "next": self.get_next_link(self.parse_query_params()),
                "previous": self.get_previous_link(self.parse_query_params()),
                "data": data,
            },
            status=status,
        )

    def get_next_link(self, query_params):
        if not self.page.has_next():
            return None
        page_number = self.page.next_page_number()
        url = self.host + self.url_suffix
        if query_params:
            url = f"{self.host}{self.url_suffix}?{query_params}"
        return replace_query_param(url, self.page_query_param, page_number)

    def get_previous_link(self, query_params):
        if not self.page.has_previous():
            return None
        page_number = self.page.previous_page_number()
        url = self.host + self.url_suffix
        if query_params:
            url = f"{self.host}{self.url_suffix}?{query_params}"
        return replace_query_param(url, self.page_query_param, page_number)

    def parse_query_params(self):
        request_params = self.request.query_params
        if not request_params:
            return None
        query_str = ""
        query_str_list = list(request_params.items())
        for index, value in enumerate(request_params.items()):
            if (index + 1) == len(query_str_list):
                query_str += f"{value[0]}={value[1]}"
                break
            query_str += f"{value[0]}={value[1]}&"
        return query_str


class SendEmail:
    from_email = settings.DEFAULT_FROM_EMAIL

    def __init__(self, template=None, subject=None, to_emails=[], context={}):
        self.template = template
        self.to_email = to_emails
        self.context = context
        self.subject = subject

    def _compose_mail(self):
        message = EmailMessage(
            subject=self.subject,
            body=render_to_string(self.template, self.context),
            from_email=self.from_email,
            to=self.to_email,
        )
        message.content_subtype = "html"
        return message

    def send(self):
        mail = self._compose_mail()
        return mail.send(fail_silently=False)


class OnePipeProvider:
    ONEPIPE_BASE_URL = settings.ONEPIPE_BASE_URL
    ONEPIPE_SECRET_KEY = settings.ONEPIPE_SECRET_KEY
    ONEPIPE_API_KEY = settings.ONEPIPE_API_KEY
    ONEPIPE_ENCRYPT_SERVICE_ENDPOINT = settings.ENCRYPT_SERVICE_ENDPOINT

    @classmethod
    def perform_card_debit(
        cls,
        request_ref=None,
        txn_ref=None,
        txn_amt=None,
        customer_data={},
        secured_card=None,
        txn_meta={},
        **kwargs,
    ):
        try:
            payment_data = {
                "request_ref": request_ref,
                "request_type": "collect",
                "auth": {
                    "type": "card",
                    "secure": secured_card,
                    "auth_provider": "Quickteller",
                    "route_mode": None,
                },
                "transaction": {
                    "mock_mode": "inspect",
                    "transaction_ref": txn_ref,
                    "transaction_desc": "A random transaction",
                    "transaction_ref_parent": "",
                    "amount": txn_amt,
                    "customer": customer_data,
                    "meta": txn_meta,
                    "details": None,
                },
            }
            signature = hashlib.md5(
                f"{request_ref};{cls.ONEPIPE_SECRET_KEY}".encode()
            ).hexdigest()
            response = requests.post(
                url=cls.ONEPIPE_BASE_URL + "/v2/transact",
                json=payment_data,
                headers=dict(
                    Authorization=f"Bearer {cls.ONEPIPE_API_KEY}", Signature=signature
                ),
                timeout=20,
            )
            if not response.ok:
                return None

            response_data = response.json()
            if response_data["status"] == "Successful":
                return response.json()
        except:
            return None

    # u2MwHlU6Bf3RRhFH
    # "507850785078507812;081;0222;1111"
    # Pan:5061040000000000306 Pin:1234 CVV:123 EXP:1901
    # Pan:5061040000000000306;123;0119;1234    Pin:1234 CVV:123 EXP:1901

    @classmethod
    def encrypt_card_data(cls, card_data):
        if not settings.IS_PROD_ENV:
            return "xUf/5mBSVGbDM8PzBd2rrXnlS5ht2OPn23Ccg8RGmvpaW7bP/4Z2uA=="
        try:
            response = requests.post(
                url=cls.ONEPIPE_ENCRYPT_SERVICE_ENDPOINT,
                json={"cardData": card_data},
                timeout=30,
            )
            if not response.ok:
                return None
            return response.json()["data"]
        except:
            return None


class ChannelManager:
    """ Manages how data is sent from the server to websocket channel """

    @staticmethod
    def ws_publish(
        channel: str, handler: str = "server_event_trigger", payload: dict = None
    ):
        """ Sends message to the websocket group """
        async_to_sync(channel_layer.group_send)(
            channel,
            {"type": handler, "event_data": payload},
        )

    @staticmethod
    def push_notify():
        pass

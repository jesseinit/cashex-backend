from rest_framework.exceptions import APIException
from rest_framework.status import (
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)


class DistanceMatrixException(APIException):
    status_code = HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = {"error": "Distance Matrix service is down. Retry again"}


class UnavailableResourceException(APIException):
    status_code = HTTP_503_SERVICE_UNAVAILABLE
    default_detail = {"error": "This resource is down. Retry again"}

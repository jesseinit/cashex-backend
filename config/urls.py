"""config URL Configuration
The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include
from config.base_view import BaseView
from userservice.views import EmailVerficationView
import debug_toolbar


urlpatterns = [
    path("debug/", include(debug_toolbar.urls)),
    path("api/v1/", include("userservice.urls")),
    path("api/v1/", include("transactionservice.urls")),
    path("api/v1/", include("paymentservice.urls")),
    path("", BaseView.as_view(), name="base_url"),
    path(
        "email-verification/<regcode>",
        EmailVerficationView.as_view(),
        name="email-verification",
    ),
]

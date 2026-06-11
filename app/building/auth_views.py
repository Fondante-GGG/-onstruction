import requests

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView


class RemoteLoginView(APIView):
    """Proxy login to NurCRM and store the access token in a Building cookie."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    parser_classes = [JSONParser, FormParser]

    def post(self, request):
        try:
            upstream = requests.post(
                settings.NURCRM_AUTH_URL,
                json=request.data,
                timeout=settings.NURCRM_REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            return Response(
                {"detail": "NurCRM auth service is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            data = upstream.json()
        except ValueError:
            data = {"detail": upstream.text or "NurCRM auth response is not valid JSON."}

        if upstream.status_code >= 400:
            return Response(data, status=upstream.status_code)

        access_token = data.get("access")
        if not access_token:
            return Response(
                {"detail": "NurCRM auth response has no access token."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        body = {key: value for key, value in data.items() if key not in {"access", "refresh"}}
        body.setdefault("detail", "Authenticated.")
        response = Response(body, status=upstream.status_code)
        response.set_cookie(
            settings.BUILDING_ACCESS_COOKIE_NAME,
            access_token,
            max_age=settings.BUILDING_ACCESS_COOKIE_MAX_AGE,
            httponly=True,
            secure=settings.BUILDING_ACCESS_COOKIE_SECURE,
            samesite=settings.BUILDING_ACCESS_COOKIE_SAMESITE,
            path="/",
        )
        return response


class RemoteLogoutView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        response = Response({"detail": "Logged out."}, status=status.HTTP_200_OK)
        response.delete_cookie(settings.BUILDING_ACCESS_COOKIE_NAME, path="/")
        return response

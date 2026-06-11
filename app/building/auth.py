import requests

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed


class NurCRMTokenAuthentication(authentication.BaseAuthentication):
    """
    Authenticates Building requests through NurCRM.

    The access token can come from either:
    - Authorization: Bearer <token>
    - HttpOnly cookie configured by BUILDING_ACCESS_COOKIE_NAME
    """

    keyword = "Bearer"

    def authenticate(self, request):
        token = self._get_token(request)
        if not token:
            return None

        profile = self._fetch_profile(token)
        user = get_user_model().objects.sync_from_profile(profile)
        request.nurcrm_profile = profile
        request.nurcrm_access_token = token
        return user, token

    def authenticate_header(self, request):
        return self.keyword

    def _get_token(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if header:
            parts = header.split()
            if len(parts) == 2 and parts[0].lower() == self.keyword.lower():
                return parts[1]
            raise AuthenticationFailed("Invalid Authorization header. Use: Bearer <token>.")
        return request.COOKIES.get(settings.BUILDING_ACCESS_COOKIE_NAME)

    def _fetch_profile(self, token):
        try:
            response = requests.get(
                settings.NURCRM_PROFILE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=settings.NURCRM_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthenticationFailed("NurCRM auth service is unavailable.") from exc

        if response.status_code in (401, 403):
            raise AuthenticationFailed("NurCRM token is invalid or expired.")
        if response.status_code >= 400:
            raise AuthenticationFailed("NurCRM profile request failed.")

        try:
            data = response.json()
        except ValueError as exc:
            raise AuthenticationFailed("NurCRM profile response is not valid JSON.") from exc

        if not isinstance(data, dict):
            raise AuthenticationFailed("NurCRM profile response has invalid format.")
        return data

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        login_value = username or kwargs.get(user_model.USERNAME_FIELD)
        if not login_value or not password:
            return None

        lookup = {user_model.USERNAME_FIELD: login_value}
        if "@" in login_value:
            lookup = {"email__iexact": login_value}

        try:
            user = user_model.objects.get(**lookup)
        except user_model.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

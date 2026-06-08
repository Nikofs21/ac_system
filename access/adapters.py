from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Bloquea registro público y login con contraseña."""

    def is_open_for_signup(self, request):
        return False

    def login(self, request, user):
        # Solo permite login si tiene cuenta social conectada
        from allauth.socialaccount.models import SocialAccount
        if not SocialAccount.objects.filter(user=user).exists():
            raise PermissionDenied
        super().login(request, user)


class NoNewUsersAdapter(DefaultSocialAccountAdapter):
    """Solo permite OAuth a usuarios ya registrados en el sistema."""

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return

        email = sociallogin.account.extra_data.get('email', '')
        if email:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(email__iexact=email)
                sociallogin.connect(request, user)
                return
            except User.DoesNotExist:
                pass

        raise ImmediateHttpResponse(
            redirect('/login/?error=no_account')
        )
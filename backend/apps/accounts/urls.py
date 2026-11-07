from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view(), name="csrf"),
    path("config/", views.AuthConfigView.as_view(), name="auth-config"),
    path("oauth/<str:provider>/start/", views.OAuthStartView.as_view(), name="oauth-start"),
    path(
        "oauth/<str:provider>/callback/", views.OAuthCallbackView.as_view(), name="oauth-callback"
    ),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("password/", views.PasswordChangeView.as_view(), name="password-change"),
    path("email/", views.EmailChangeView.as_view(), name="email-change"),
    path("email/confirm/", views.EmailChangeConfirmView.as_view(), name="email-change-confirm"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("session/", views.SessionView.as_view(), name="session"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path("verify-email/resend/", views.ResendVerificationView.as_view(), name="verify-resend"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password-reset"),
    path(
        "password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]

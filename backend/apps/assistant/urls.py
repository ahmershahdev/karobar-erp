from django.urls import path

from . import views

urlpatterns = [
    path("messages/", views.ChatMessagesView.as_view(), name="assistant-messages"),
    path("ask/", views.ChatAskView.as_view(), name="assistant-ask"),
    path("check/", views.ChatCheckView.as_view(), name="assistant-check"),
    path("reset/", views.ChatResetView.as_view(), name="assistant-reset"),
]

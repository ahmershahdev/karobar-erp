from typing import Any, cast

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.tenancy.permissions import IsTenantMember, membership_of

from . import services
from .models import ChatMessage

MAX_QUESTION = 2000
SHOWN = 50


class ChatMessageSerializer(serializers.ModelSerializer[ChatMessage]):
    class Meta:
        model = ChatMessage
        fields = ("id", "role", "content", "created_at", "signature")


class ChatAskSerializer(serializers.Serializer[Any]):
    message = serializers.CharField(max_length=MAX_QUESTION, trim_whitespace=True)
    # The language the app is shown in, so screen names match the person's screen.
    language = serializers.ChoiceField(choices=services.LANGUAGES, default="en")


class ChatCheckSerializer(serializers.Serializer[Any]):
    enabled = serializers.BooleanField()
    ok = serializers.BooleanField()
    count = serializers.IntegerField()
    broken_at = serializers.IntegerField(allow_null=True)


class AssistantUnavailable(APIException):
    status_code = 503
    default_detail = services.AssistantError.message
    default_code = "assistant_unavailable"


def actor(request: Request) -> User:
    return cast(User, request.user)


class ChatMessagesView(APIView):
    permission_classes = [IsTenantMember]
    throttle_scope = "tenancy"

    @extend_schema(responses=ChatMessageSerializer(many=True))
    def get(self, request: Request) -> Response:
        newest = services.current(actor(request)).order_by("-id")[:SHOWN]
        return Response(ChatMessageSerializer(list(newest)[::-1], many=True).data)


class ChatAskView(APIView):
    permission_classes = [IsTenantMember]
    throttle_scope = "assistant"

    @extend_schema(request=ChatAskSerializer, responses=ChatMessageSerializer)
    def post(self, request: Request) -> Response:
        body = ChatAskSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            answer = services.ask(
                actor(request),
                membership_of(request),
                body.validated_data["message"],
                body.validated_data["language"],
            )
        except services.AssistantError as exc:
            raise AssistantUnavailable(type(exc).message) from exc
        return Response(ChatMessageSerializer(answer).data)


class ChatResetView(APIView):
    permission_classes = [IsTenantMember]
    throttle_scope = "tenancy"

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        services.reset(actor(request))
        return Response(status=204)


class ChatCheckView(APIView):
    permission_classes = [IsTenantMember]
    throttle_scope = "tenancy"

    @extend_schema(responses=ChatCheckSerializer)
    def get(self, request: Request) -> Response:
        data = {"enabled": bool(settings.GROQ_API_KEY), **services.verify(actor(request))}
        return Response(ChatCheckSerializer(data).data)

from typing import Any, cast

from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.tenancy.permissions import IsTenantMember, membership_of

from . import drafts, services
from .models import ChatMessage

MAX_QUESTION = 2000
SHOWN = 50


class CardPartySerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()


class CardLineSerializer(serializers.Serializer[Any]):
    product = serializers.IntegerField()
    name = serializers.CharField()
    sku = serializers.CharField()
    unit = serializers.IntegerField()
    unit_code = serializers.CharField()
    quantity = serializers.CharField()
    unit_price = serializers.CharField(allow_null=True)


class CardProblemSerializer(serializers.Serializer[Any]):
    code = serializers.ChoiceField(
        choices=["unclear", "not_found", "ambiguous", "no_warehouse", "too_many", "not_allowed"]
    )
    field = serializers.CharField()
    name = serializers.CharField()
    options = serializers.ListField(child=serializers.CharField())


class CardSerializer(serializers.Serializer[Any]):
    """A proposed draft, a draft that couldn't be made, or the record that one was confirmed."""

    kind = serializers.ChoiceField(choices=list(drafts.KINDS), required=False)
    party = CardPartySerializer(required=False)
    warehouse = CardPartySerializer(required=False)
    lines = CardLineSerializer(many=True, required=False)
    memo = serializers.CharField(required=False)
    total = serializers.CharField(required=False)
    problem = CardProblemSerializer(required=False)
    draft = serializers.IntegerField(required=False, help_text="On a done row: the card's id.")
    document = serializers.IntegerField(required=False, help_text="The saved draft's id.")


class ChatMessageSerializer(serializers.ModelSerializer[ChatMessage]):
    card = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ("id", "role", "content", "created_at", "signature", "card")

    @extend_schema_field(CardSerializer(allow_null=True))
    def get_card(self, message: ChatMessage) -> Any:
        if message.role not in (ChatMessage.Role.DRAFT, ChatMessage.Role.DONE):
            return None
        return services.load(message)


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


class AlreadyConfirmed(APIException):
    status_code = 409
    default_detail = "This draft was already saved. Open it from its screen."
    default_code = "already_confirmed"


class ChatConfirmView(APIView):
    permission_classes = [IsTenantMember]
    throttle_scope = "tenancy"

    @extend_schema(request=None, responses=ChatMessageSerializer)
    def post(self, request: Request, pk: int) -> Response:
        try:
            done = services.confirm(request, actor(request), membership_of(request), pk)
        except services.DraftGoneError as exc:
            raise NotFound from exc
        except services.AlreadyDoneError as exc:
            raise AlreadyConfirmed from exc
        except drafts.NotAllowedError as exc:
            raise PermissionDenied(
                "Your role can no longer make this kind of document. Ask the owner."
            ) from exc
        return Response(ChatMessageSerializer(done).data)


class ChatCheckView(APIView):
    permission_classes = [IsTenantMember]
    throttle_scope = "tenancy"

    @extend_schema(responses=ChatCheckSerializer)
    def get(self, request: Request) -> Response:
        data = {"enabled": bool(settings.GROQ_API_KEY), **services.verify(actor(request))}
        return Response(ChatCheckSerializer(data).data)

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from .models import Account, FiscalPeriod, FiscalYear, JournalEntry, JournalLine, TaxRate


class TenantAccountField(serializers.PrimaryKeyRelatedField[Account]):
    # Resolved per request, after the tenant is active, so only this tenant's accounts match.
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(queryset=Account.all_tenants.none(), **kwargs)

    def get_queryset(self) -> Any:
        return Account.objects.all()


# `parent` is left to ModelSerializer on purpose: declaring it here would shadow the
# Field.parent attribute DRF uses internally. The generated field queries the tenant-scoped
# default manager when it validates, so it only accepts this tenant's accounts.
class TaxRateSerializer(serializers.ModelSerializer[TaxRate]):
    class Meta:
        model = TaxRate
        fields = ("id", "name", "rate", "valid_from", "valid_to", "source")
        extra_kwargs = {
            "rate": {"min_value": Decimal(0), "max_value": Decimal(100)},
            "valid_to": {"required": False, "allow_null": True},
        }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Documents point at this row, so what it says must never change under them. A new
        # percentage is a new rate: end this one and add the next.
        if self.instance is not None:
            for field in ("rate", "valid_from"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError(
                        {field: "End this rate and add a new one instead."}
                    )
        start = attrs.get("valid_from") or getattr(self.instance, "valid_from", None)
        end = attrs.get("valid_to", getattr(self.instance, "valid_to", None))
        if start and end and end < start:
            raise serializers.ValidationError({"valid_to": "The end date is before the start."})
        return attrs


class AccountSerializer(serializers.ModelSerializer[Account]):
    class Meta:
        model = Account
        fields = ("id", "code", "name", "type", "parent", "is_group", "is_active", "role")
        read_only_fields = ("id", "role")
        extra_kwargs = {"code": {"max_length": 20}, "name": {"max_length": 150}}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if parent is not None:
            if not parent.is_group:
                raise serializers.ValidationError({"parent": ["The parent must be a group."]})
            if self.instance is not None and self._descends_from(parent, self.instance):
                raise serializers.ValidationError(
                    {"parent": ["An account can't sit under itself or one of its own accounts."]}
                )
        return attrs

    @staticmethod
    def _descends_from(candidate: Account, account: Account) -> bool:
        """True when `candidate` is `account` or sits somewhere below it."""
        seen: set[int] = set()
        node: Account | None = candidate
        while node is not None and node.pk not in seen:
            if node.pk == account.pk:
                return True
            seen.add(node.pk)
            node = node.parent
        return False


class FiscalPeriodSerializer(serializers.ModelSerializer[FiscalPeriod]):
    closed = serializers.SerializerMethodField()

    class Meta:
        model = FiscalPeriod
        fields = ("id", "number", "start", "end", "closed")
        read_only_fields = fields

    def get_closed(self, period: FiscalPeriod) -> bool:
        return period.closed_at is not None


class FiscalYearSerializer(serializers.ModelSerializer[FiscalYear]):
    periods = FiscalPeriodSerializer(many=True, read_only=True)

    class Meta:
        model = FiscalYear
        fields = ("id", "name", "start", "end", "periods")
        read_only_fields = ("id", "periods")
        extra_kwargs = {"name": {"required": False, "allow_blank": True, "max_length": 40}}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["end"] < attrs["start"]:
            raise serializers.ValidationError({"end": ["The year can't end before it starts."]})
        return attrs


class PeriodStateSerializer(serializers.Serializer[None]):
    closed = serializers.BooleanField()


class JournalLineSerializer(serializers.ModelSerializer[JournalLine]):
    account = TenantAccountField()
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = JournalLine
        fields = (
            "id",
            "account",
            "account_code",
            "account_name",
            "debit",
            "credit",
            "description",
        )
        read_only_fields = ("id", "account_code", "account_name")
        extra_kwargs = {
            "debit": {"min_value": 0, "required": False},
            "credit": {"min_value": 0, "required": False},
            "description": {"required": False, "max_length": 255},
        }


class JournalEntrySerializer(serializers.ModelSerializer[JournalEntry]):
    lines = JournalLineSerializer(many=True)
    created_by = serializers.EmailField(source="created_by.email", read_only=True)
    posted_by = serializers.EmailField(
        source="posted_by.email", read_only=True, default=None, allow_null=True
    )
    reversal_of = serializers.PrimaryKeyRelatedField[JournalEntry](read_only=True, allow_null=True)
    reversed_by = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = (
            "id",
            "number",
            "date",
            "memo",
            "status",
            "lines",
            "total",
            "reversal_of",
            "reversed_by",
            "created_by",
            "posted_by",
            "posted_at",
        )
        read_only_fields = ("id", "number", "status", "posted_at")
        extra_kwargs = {"memo": {"required": False, "max_length": 255}}

    def validate_lines(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > 500:
            raise serializers.ValidationError("An entry can have at most 500 lines.")
        return value

    def get_reversed_by(self, entry: JournalEntry) -> int | None:
        reversal = getattr(entry, "reversed_by", None)
        return reversal.pk if reversal is not None else None

    def get_total(self, entry: JournalEntry) -> str:
        return str(sum((line.debit for line in entry.lines.all()), start=0))


class ReverseSerializer(serializers.Serializer[None]):
    date = serializers.DateField()
    memo = serializers.CharField(max_length=255, required=False, allow_blank=True)


class ReportQuerySerializer(serializers.Serializer[None]):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    export = serializers.ChoiceField(choices=["csv"], required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start, end = attrs.get("start"), attrs.get("end")
        if start and end and end < start:
            raise serializers.ValidationError({"end": ["The end can't be before the start."]})
        return attrs

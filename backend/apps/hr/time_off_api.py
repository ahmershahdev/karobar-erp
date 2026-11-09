"""Serializers and views for the working week, holidays, leave and attendance."""

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.inventory import services as inventory
from apps.inventory.serializers import scoped

from . import time_off
from .models import Attendance, Employee, Holiday, HrSettings, LeaveRequest, LeaveType
from .views import HrView, actor, run

# Serializers


class HrSettingsSerializer(serializers.ModelSerializer[HrSettings]):
    weekend = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), max_length=6
    )
    holiday_country = serializers.ChoiceField(choices=list(time_off.COUNTRIES))

    class Meta:
        model = HrSettings
        fields = (
            "weekend",
            "holiday_country",
            "id_retention_years",
            "default_province",
            "wps_employer_id",
            "wps_bank_code",
        )
        extra_kwargs = {
            "id_retention_years": {"min_value": 6, "max_value": 50},
            "default_province": {"required": False},
            "wps_employer_id": {"required": False},
            "wps_bank_code": {"required": False},
        }

    def validate_wps_employer_id(self, value: str) -> str:
        code = value.strip()
        if code and not (code.isascii() and code.isdigit()):
            raise serializers.ValidationError("The MOL establishment ID is digits only.")
        return code

    def validate_wps_bank_code(self, value: str) -> str:
        code = value.strip()
        if code and not (code.isascii() and code.isdigit() and len(code) == 9):
            raise serializers.ValidationError("A routing code is 9 digits.")
        return code


class HolidaySerializer(serializers.ModelSerializer[Holiday]):
    class Meta:
        model = Holiday
        fields = ("id", "on", "name", "source")
        extra_kwargs = {"source": {"required": False}}


class FillSerializer(serializers.Serializer[Any]):
    year = serializers.IntegerField(min_value=2000, max_value=2100)


class FilledSerializer(serializers.Serializer[Any]):
    added = serializers.IntegerField()


class LeaveTypeSerializer(serializers.ModelSerializer[LeaveType]):
    class Meta:
        model = LeaveType
        fields = ("id", "name", "paid", "days_per_year", "is_active")
        extra_kwargs = {
            "days_per_year": {"min_value": Decimal(0), "max_value": Decimal(366)},
            "paid": {"required": False},
            "is_active": {"required": False},
        }


class LeaveRequestSerializer(serializers.ModelSerializer[LeaveRequest]):
    employee = scoped(Employee)
    leave_type = scoped(LeaveType)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = (
            "id",
            "employee",
            "employee_name",
            "leave_type",
            "leave_type_name",
            "starts_on",
            "ends_on",
            "days",
            "status",
            "note",
            "decided_at",
        )
        read_only_fields = ("id", "days", "status", "decided_at")
        extra_kwargs = {"note": {"required": False}}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["ends_on"] < attrs["starts_on"]:
            raise serializers.ValidationError({"ends_on": ["Leave can't end before it starts."]})
        return attrs


class BalanceSerializer(serializers.Serializer[Any]):
    leave_type = serializers.IntegerField(source="leave_type.pk")
    name = serializers.CharField(source="leave_type.name")
    paid = serializers.BooleanField(source="leave_type.paid")
    allowed = serializers.DecimalField(max_digits=5, decimal_places=1)
    taken = serializers.DecimalField(max_digits=5, decimal_places=1)
    pending = serializers.DecimalField(max_digits=5, decimal_places=1)
    left = serializers.DecimalField(max_digits=5, decimal_places=1, allow_null=True)


class DayRowSerializer(serializers.Serializer[Any]):
    employee = scoped(Employee)
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class MarkDaySerializer(serializers.Serializer[Any]):
    on = serializers.DateField()
    rows = DayRowSerializer(many=True)

    def validate_rows(self, value: list[Any]) -> list[Any]:
        if len(value) > time_off.MAX_ATTENDANCE_ROWS:
            raise serializers.ValidationError("Too many people in one go.")
        return value


class DayEntrySerializer(serializers.Serializer[Any]):
    employee = serializers.IntegerField()
    code = serializers.CharField()
    full_name = serializers.CharField()
    status = serializers.CharField()
    note = serializers.CharField()
    on_leave = serializers.BooleanField()


class DaySerializer(serializers.Serializer[Any]):
    on = serializers.DateField()
    working_day = serializers.BooleanField()
    holiday = serializers.CharField(allow_null=True)
    people = DayEntrySerializer(many=True)


class MarkedSerializer(serializers.Serializer[Any]):
    changed = serializers.IntegerField()


# Views


class HrSettingsView(HrView):
    @extend_schema(responses=HrSettingsSerializer)
    def get(self, request: Request) -> Response:
        return Response(HrSettingsSerializer(time_off.settings_for()).data)

    @extend_schema(request=HrSettingsSerializer, responses=HrSettingsSerializer)
    def patch(self, request: Request) -> Response:
        body = HrSettingsSerializer(time_off.settings_for(), data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        saved = run(time_off.save_settings, actor(request), body.validated_data)
        return Response(HrSettingsSerializer(saved).data)


@extend_schema(parameters=[OpenApiParameter("year", int)])
class HolidayListView(HrView, generics.ListCreateAPIView[Holiday]):
    serializer_class = HolidaySerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Holiday]:
        query = Holiday.objects.all()
        year = self.request.query_params.get("year", "")
        if year.isdigit() and len(year) == 4:
            query = query.filter(on__year=int(year))
        return query

    def perform_create(self, serializer: HolidaySerializer) -> None:  # type: ignore[override]
        serializer.instance = run(
            time_off.save_holiday, actor(self.request), Holiday(), serializer.validated_data
        )


class HolidayDetailView(HrView, generics.RetrieveUpdateDestroyAPIView[Holiday]):
    serializer_class = HolidaySerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Holiday]:
        return Holiday.objects.all()

    def perform_update(self, serializer: HolidaySerializer) -> None:  # type: ignore[override]
        run(
            time_off.save_holiday,
            actor(self.request),
            serializer.instance,
            serializer.validated_data,
        )

    def perform_destroy(self, instance: Holiday) -> None:
        run(inventory.delete_master, actor(self.request), instance)


class HolidayFillView(HrView):
    required_action = "create"

    @extend_schema(request=FillSerializer, responses=FilledSerializer)
    def post(self, request: Request) -> Response:
        body = FillSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        added = run(time_off.fill_holidays, actor(request), body.validated_data["year"])
        return Response({"added": added})


class LeaveTypeListView(HrView, generics.ListCreateAPIView[LeaveType]):
    serializer_class = LeaveTypeSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[LeaveType]:
        return LeaveType.objects.all()

    def perform_create(self, serializer: LeaveTypeSerializer) -> None:  # type: ignore[override]
        serializer.instance = run(
            inventory.save_master, actor(self.request), LeaveType(), serializer.validated_data
        )


class LeaveTypeDetailView(HrView, generics.RetrieveUpdateDestroyAPIView[LeaveType]):
    serializer_class = LeaveTypeSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[LeaveType]:
        return LeaveType.objects.all()

    def perform_update(self, serializer: LeaveTypeSerializer) -> None:  # type: ignore[override]
        run(
            inventory.save_master,
            actor(self.request),
            serializer.instance,
            serializer.validated_data,
        )

    def perform_destroy(self, instance: LeaveType) -> None:
        run(inventory.delete_master, actor(self.request), instance)


def _leave() -> QuerySet[LeaveRequest]:
    return LeaveRequest.objects.select_related("employee", "leave_type")


@extend_schema(
    parameters=[
        OpenApiParameter("employee", int),
        OpenApiParameter("status", str, enum=[s.value for s in LeaveRequest.Status]),
    ]
)
class LeaveListView(HrView, generics.ListCreateAPIView[LeaveRequest]):
    serializer_class = LeaveRequestSerializer

    def get_queryset(self) -> QuerySet[LeaveRequest]:
        query = _leave()
        params = self.request.query_params
        if params.get("employee", "").isdigit():
            query = query.filter(employee_id=params["employee"])
        if params.get("status") in LeaveRequest.Status.values:
            query = query.filter(status=params["status"])
        return query

    def perform_create(self, serializer: LeaveRequestSerializer) -> None:  # type: ignore[override]
        created = run(time_off.ask_leave, actor(self.request), serializer.validated_data)
        serializer.instance = _leave().get(pk=created.pk)


class LeaveDetailView(HrView, generics.RetrieveDestroyAPIView[LeaveRequest]):
    serializer_class = LeaveRequestSerializer

    def get_queryset(self) -> QuerySet[LeaveRequest]:
        return _leave()

    def perform_destroy(self, instance: LeaveRequest) -> None:
        run(time_off.withdraw_leave, actor(self.request), instance)


class LeaveDecisionView(HrView, generics.GenericAPIView[LeaveRequest]):
    """Approving or refusing leave is a decision like posting, so it needs the post right."""

    required_action = "post"
    approve = True

    def get_queryset(self) -> QuerySet[LeaveRequest]:
        return _leave()

    @extend_schema(request=None, responses=LeaveRequestSerializer)
    def post(self, request: Request, pk: int) -> Response:
        decided = run(time_off.decide_leave, actor(request), self.get_object(), self.approve)
        return Response(LeaveRequestSerializer(_leave().get(pk=decided.pk)).data)


class CancelLeaveSerializer(serializers.Serializer[Any]):
    # The first day back at work, for someone who came back early. Empty cancels all of it.
    back_on = serializers.DateField(required=False, allow_null=True)


class LeaveCancelView(HrView, generics.GenericAPIView[LeaveRequest]):
    """Cancelling approved leave undoes a decision, so it needs the post right like approving."""

    required_action = "post"

    def get_queryset(self) -> QuerySet[LeaveRequest]:
        return _leave()

    @extend_schema(request=CancelLeaveSerializer, responses=LeaveRequestSerializer)
    def post(self, request: Request, pk: int) -> Response:
        target = self.get_object()
        body = CancelLeaveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        done = run(
            time_off.cancel_leave, actor(request), target, body.validated_data.get("back_on")
        )
        return Response(LeaveRequestSerializer(_leave().get(pk=done.pk)).data)


class LeaveBalanceView(HrView):
    @extend_schema(
        parameters=[
            OpenApiParameter("employee", int, required=True),
            OpenApiParameter("year", int),
        ],
        responses=BalanceSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        params = request.query_params
        employee_id = params.get("employee", "")
        employee = Employee.objects.filter(
            pk=int(employee_id) if employee_id.isdigit() else 0
        ).first()
        if employee is None:
            raise NotFound
        year_text = params.get("year", "")
        year = (
            int(year_text)
            if year_text.isdigit() and len(year_text) == 4
            else timezone.localdate().year
        )
        return Response(BalanceSerializer(time_off.balances(employee, year), many=True).data)


class AttendanceView(HrView):
    @extend_schema(parameters=[OpenApiParameter("date", str)], responses=DaySerializer)
    def get(self, request: Request) -> Response:
        on: date = serializers.DateField().to_internal_value(
            request.query_params.get("date") or str(timezone.localdate())
        )
        settings = time_off.settings_for()
        holiday = Holiday.objects.filter(on=on).first()
        marked = {a.employee_id: a for a in Attendance.objects.filter(on=on)}
        leave = time_off.on_leave(on)
        people = [
            {
                "employee": person.pk,
                "code": person.code,
                "full_name": person.full_name,
                "status": marked[person.pk].status if person.pk in marked else "present",
                "note": marked[person.pk].note if person.pk in marked else "",
                "on_leave": person.pk in leave,
            }
            for person in time_off.working(on).order_by("full_name")
        ]
        data = {
            "on": on,
            "working_day": on.weekday() not in settings.weekend and holiday is None,
            "holiday": holiday.name if holiday else None,
            "people": people,
        }
        return Response(DaySerializer(data).data)

    @extend_schema(request=MarkDaySerializer, responses=MarkedSerializer)
    def post(self, request: Request) -> Response:
        body = MarkDaySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        rows = [
            time_off.DayRow(row["employee"], row["status"], row.get("note", ""))
            for row in body.validated_data["rows"]
        ]
        changed = run(time_off.mark_day, actor(request), body.validated_data["on"], rows)
        return Response({"changed": changed})

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.inventory.models import money_field, percent_field
from apps.tenancy.models import TenantOwnedModel


class Department(TenantOwnedModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_department")]

    def __str__(self) -> str:
        return self.name


class SalaryStructure(TenantOwnedModel):
    """A named set of allowances and deductions on top of a basic salary, shared by every
    contract that uses it, so a change to the house rent rule is made once."""

    name = models.CharField(max_length=80)
    note = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_salary_structure")
        ]

    def __str__(self) -> str:
        return self.name


class SalaryComponent(TenantOwnedModel):
    class Kind(models.TextChoices):
        EARNING = "earning"
        DEDUCTION = "deduction"

    structure = models.ForeignKey(
        SalaryStructure, on_delete=models.CASCADE, related_name="components"
    )
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # One of these two: a fixed amount a month, or a percentage of basic salary.
    amount = money_field(null=True, blank=True)
    percent = percent_field()
    taxable = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__isnull=False, percent__isnull=True)
                | Q(amount__isnull=True, percent__isnull=False),
                name="component_amount_or_percent",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Province(models.TextChoices):
    """Where in Pakistan someone works. Minimum wages and social security are set per province,
    so this picks which figures apply."""

    ICT = "ICT", "Islamabad Capital Territory"
    PUNJAB = "PB", "Punjab"
    SINDH = "SD", "Sindh"
    KP = "KP", "Khyber Pakhtunkhwa"
    BALOCHISTAN = "BA", "Balochistan"
    AJK = "AJK", "Azad Jammu and Kashmir"
    GB = "GB", "Gilgit-Baltistan"


class Employee(TenantOwnedModel):
    code = models.CharField(max_length=20)
    full_name = models.CharField(max_length=150)
    job_title = models.CharField(max_length=100, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, blank=True, related_name="employees"
    )
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    # The national identity number (CNIC in Pakistan, Emirates ID in the UAE). Payroll tax needs
    # it; it is shown only to people with HR rights and never leaves the business.
    national_id = models.CharField(max_length=30, blank=True)
    # Where the salary is paid, for the bank transfer list.
    bank_account = models.CharField(max_length=50, blank=True)
    joined_on = models.DateField()
    # Set when someone leaves. Employees are never deleted once they have a contract, because
    # payslips and journal entries refer to them.
    left_on = models.DateField(null=True, blank=True)
    province = models.CharField(max_length=3, choices=Province.choices, blank=True)
    # Off until the business says so: EOBI covers businesses with five or more staff and stops
    # at pension age, and provincial social security has its own wage limit. Neither can be
    # judged from the records kept here.
    pays_eobi = models.BooleanField(default=False)
    pays_social_security = models.BooleanField(default=False)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_employee_code"),
            models.CheckConstraint(
                condition=Q(left_on__isnull=True) | Q(left_on__gte=F("joined_on")),
                name="employee_leaves_after_joining",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.full_name}"


class Contract(TenantOwnedModel):
    """What one employee is paid over a period. Contracts for one person never overlap, so the
    pay on any day is never in doubt."""

    class Kind(models.TextChoices):
        PERMANENT = "permanent"
        FIXED_TERM = "fixed_term"
        PROBATION = "probation"

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="contracts")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.PERMANENT)
    starts_on = models.DateField()
    # Empty means it runs until it is ended.
    ends_on = models.DateField(null=True, blank=True)
    structure = models.ForeignKey(
        SalaryStructure, on_delete=models.PROTECT, related_name="contracts"
    )
    basic_salary = money_field()
    note = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-starts_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__isnull=True) | Q(ends_on__gte=F("starts_on")),
                name="contract_ends_after_start",
            ),
            models.CheckConstraint(condition=Q(basic_salary__gte=0), name="basic_not_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} from {self.starts_on}"


def _sunday() -> list[int]:
    return [6]


class HrSettings(TenantOwnedModel):
    """How this business's working week and records work. One row per business; until it is
    saved, the defaults apply."""

    # Weekday numbers as Python counts them: Monday is 0, Sunday is 6.
    weekend = models.JSONField(default=_sunday)
    # Which country's public holidays to start the list from. The list itself is data the
    # business can change, because moon-sighted holidays are only estimates in advance.
    holiday_country = models.CharField(max_length=2, default="PK")
    # How long after the end of the tax year someone left in their national ID is kept. Six is
    # the shortest allowed: tax records must be kept that long.
    id_retention_years = models.PositiveSmallIntegerField(default=6)
    # The province a new employee starts in.
    default_province = models.CharField(max_length=3, choices=Province.choices, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="uniq_hr_settings"),
            models.CheckConstraint(
                condition=Q(id_retention_years__gte=6), name="id_retention_at_least_six"
            ),
        ]

    def __str__(self) -> str:
        return f"HR settings {self.tenant_id}"


class Holiday(TenantOwnedModel):
    on = models.DateField()
    name = models.CharField(max_length=100)
    # Where the date came from, such as the holidays library's estimate or a government notice.
    source = models.CharField(max_length=200, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["on"]
        constraints = [models.UniqueConstraint(fields=["tenant", "on"], name="uniq_holiday")]

    def __str__(self) -> str:
        return f"{self.on} {self.name}"


class LeaveType(TenantOwnedModel):
    name = models.CharField(max_length=60)
    paid = models.BooleanField(default=True)
    # Working days a year. Zero means no yearly limit, as for unpaid leave.
    days_per_year = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_leave_type"),
            models.CheckConstraint(condition=Q(days_per_year__gte=0), name="leave_days_positive"),
        ]

    def __str__(self) -> str:
        return self.name


class LeaveRequest(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        CANCELLED = "cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="leave")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="+")
    starts_on = models.DateField()
    ends_on = models.DateField()
    # Working days in the range, worked out when it is asked for, so a holiday added later
    # doesn't change leave already approved.
    days = models.DecimalField(max_digits=5, decimal_places=1)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=255, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-starts_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__gte=F("starts_on")), name="leave_ends_after_start"
            )
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.starts_on} to {self.ends_on}"


class Attendance(TenantOwnedModel):
    """One person on one day. A working day with no row counts as present; leave comes from
    approved leave requests, not from here."""

    class Status(models.TextChoices):
        PRESENT = "present"
        ABSENT = "absent"
        HALF_DAY = "half_day"

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="attendance")
    on = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    note = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["on", "employee_id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "employee", "on"], name="uniq_attendance")
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.on} {self.status}"

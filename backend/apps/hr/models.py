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

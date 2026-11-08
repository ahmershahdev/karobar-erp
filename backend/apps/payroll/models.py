from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.accounting.models import Account, JournalEntry
from apps.hr.models import Employee
from apps.inventory.models import money_field
from apps.tenancy.models import TenantOwnedModel


class TaxTable(TenantOwnedModel):
    """One tax year's salary slabs for one country, with the law they come from. Data, not code,
    because the Finance Act changes them every year and old payslips keep their old slabs."""

    country = models.CharField(max_length=2)
    name = models.CharField(max_length=80)
    starts_on = models.DateField()
    ends_on = models.DateField()
    source = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-starts_on", "country"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "country", "starts_on"], name="uniq_tax_table_start"
            ),
            models.CheckConstraint(
                condition=Q(ends_on__gte=F("starts_on")), name="tax_table_dates_in_order"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.country} {self.name}"


class TaxSlab(TenantOwnedModel):
    """On yearly taxable income above `over`: `fixed` plus `rate` percent of the part above."""

    table = models.ForeignKey(TaxTable, on_delete=models.CASCADE, related_name="slabs")
    over = money_field()
    fixed = money_field()
    rate = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["table_id", "over"]
        constraints = [
            models.UniqueConstraint(fields=["table", "over"], name="uniq_tax_slab_start"),
            models.CheckConstraint(
                condition=Q(over__gte=0, fixed__gte=0, rate__gte=0, rate__lte=100),
                name="tax_slab_in_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.over}: {self.fixed} + {self.rate}%"


class PayrollRun(TenantOwnedModel):
    """One month's pay for everyone. A draft can be worked out again as often as needed; posting
    fixes its payslips and books the journal entry."""

    class Status(models.TextChoices):
        DRAFT = "draft"
        POSTED = "posted"

    # The first day of the month it pays.
    month = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    # Drafts have no number yet; NULLs don't collide in the unique (tenant, number) index.
    number = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    tax_table = models.ForeignKey(
        TaxTable, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    gross = money_field(default=0)
    deductions = money_field(default=0)
    tax = money_field(default=0)
    net = money_field(default=0)
    entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    worked_out_at = models.DateTimeField(auto_now=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-month"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "month"], name="uniq_payroll_month"),
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_payroll_number"),
        ]

    def __str__(self) -> str:
        return f"Payroll {self.month:%Y-%m}"


class Payslip(TenantOwnedModel):
    """What one person was paid for one month. The lines are a copy, not a link to the salary
    structure, so a later change to the structure never rewrites a payslip."""

    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payslips")
    month_days = models.PositiveSmallIntegerField()
    paid_days = models.DecimalField(max_digits=4, decimal_places=1)
    unpaid_days = models.DecimalField(max_digits=4, decimal_places=1)
    # [{"name": "Basic", "kind": "earning", "amount": "50000.00", "taxable": true}, ...]
    lines = models.JSONField(default=list)
    gross = money_field()
    deductions = money_field()
    taxable = money_field()
    tax = money_field()
    net = money_field()
    # How the tax was reached, shown on the payslip: the year's estimated taxable salary and
    # the tax on it.
    projected_income = money_field(default=0)
    year_tax = money_field(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["run_id", "employee__code"]
        constraints = [
            models.UniqueConstraint(fields=["run", "employee"], name="uniq_payslip_person"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.run_id}"


class OpeningPay(TenantOwnedModel):
    """Taxable salary paid and tax withheld earlier in a tax year, before payroll ran here: the
    months before the business started using Karobar, or a previous employer's figures from the
    certificate a new joiner brings. Without them, the annualised method sees only part of the
    year and withholds too little."""

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="opening_pay")
    # The first day of the tax year these figures belong to.
    year_starts = models.DateField()
    taxable = money_field()
    tax = money_field()
    note = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-year_starts", "employee__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee", "year_starts"], name="uniq_opening_pay"
            ),
            models.CheckConstraint(
                condition=Q(taxable__gte=0, tax__gte=0, tax__lte=F("taxable")),
                name="opening_pay_in_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.year_starts}"


class SalaryPayment(TenantOwnedModel):
    """A posted month's net pay leaving the bank or the till, all at once. It settles salaries
    payable, so the books show the salaries as paid and the bank as lower."""

    run = models.OneToOneField(PayrollRun, on_delete=models.PROTECT, related_name="payment")
    paid_on = models.DateField()
    # The cash or bank account the money left from.
    paid_from = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    amount = money_field()
    reference = models.CharField(max_length=60, blank=True)
    entry = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="+")
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-paid_on", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="salary_payment_not_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.run_id} {self.amount}"

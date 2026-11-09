from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.accounting.models import Account, JournalEntry
from apps.hr.models import Employee, Province
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
        REVERSED = "reversed"

    # The first day of the month it pays.
    month = models.DateField()
    # The same month while the run counts, cleared when it is reversed: unique per business, so
    # a month has one live run but keeps its reversed ones as history. MySQL has no partial
    # unique index, so this is how "one live run per month" is enforced.
    live_month = models.DateField(null=True, blank=True)
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
    # EOBI and social security. The staff's share is part of `deductions`; the business's share
    # is a cost on top of the pay.
    employee_contributions = money_field(default=0)
    employer_contributions = money_field(default=0)
    # The change in everyone's end-of-service provision this month, booked with the pay.
    gratuity_change = money_field(default=0)
    entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    worked_out_at = models.DateTimeField(auto_now=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    reversal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-month", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "live_month"], name="one_live_payroll_month"
            ),
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
    # [{"scheme": "eobi", "base": "40700.00", "employer_percent": "5.00",
    #   "employee_percent": "1.00", "employer": "2035.00", "employee": "407.00"}]
    # The staff's share is also a deduction line; the business's share is not on the pay.
    contributions = models.JSONField(default=list)
    employee_contributions = money_field(default=0)
    employer_contributions = money_field(default=0)
    # The end-of-service gratuity built up by the end of this month, as if the person left
    # then with the full award, and how much that grew this month.
    gratuity_accrued = money_field(default=0)
    gratuity_change = money_field(default=0)

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


class MinimumWage(TenantOwnedModel):
    """A province's monthly minimum wage from the day a notification fixes it. It holds until a
    later one replaces it, as the notifications do: they say from when, never until when."""

    province = models.CharField(max_length=3, choices=Province.choices)
    starts_on = models.DateField()
    amount = money_field()
    source = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["province", "-starts_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "province", "starts_on"], name="uniq_minimum_wage_start"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="minimum_wage_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.province} {self.starts_on} {self.amount}"


class ContributionRate(TenantOwnedModel):
    """What EOBI or social security takes from a day on, in one province or (no province) all
    of them. Like minimum wages, a rate holds until a later one replaces it. Payslips copy the
    figures they used, so changing a rate later never rewrites a posted month."""

    class Scheme(models.TextChoices):
        EOBI = "eobi"
        SOCIAL_SECURITY = "social_security"
        GOSI_ANNUITIES = "gosi_annuities"
        GOSI_SANED = "gosi_saned"
        GOSI_HAZARDS = "gosi_hazards"
        GPSSA = "gpssa"

    class AppliesTo(models.TextChoices):
        ALL = "all"
        # Measured against the business's country: Saudis for GOSI annuities, Emiratis for
        # the UAE pension.
        NATIONALS = "nationals"
        OTHERS = "others"

    scheme = models.CharField(max_length=20, choices=Scheme.choices)
    province = models.CharField(max_length=3, choices=Province.choices, blank=True)
    starts_on = models.DateField()
    employer_percent = models.DecimalField(max_digits=5, decimal_places=2)
    employee_percent = models.DecimalField(max_digits=5, decimal_places=2)
    # True: worked out on the province's minimum wage. False: on the month's pay, up to the cap.
    on_minimum_wage = models.BooleanField(default=False)
    # True: on the basic salary and the pay parts marked as counting for social insurance, for a
    # full month. False: on the month's whole pay.
    on_insurable = models.BooleanField(default=False)
    wage_cap = money_field(null=True, blank=True)
    wage_floor = money_field(null=True, blank=True)
    applies_to = models.CharField(max_length=10, choices=AppliesTo.choices, default=AppliesTo.ALL)
    # Only for people first insured on or after this day, as GOSI's new system is.
    first_insured_from = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["scheme", "province", "-starts_on"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "tenant",
                    "scheme",
                    "province",
                    "applies_to",
                    "first_insured_from",
                    "starts_on",
                ],
                name="uniq_contribution_rate_group_start",
            ),
            models.CheckConstraint(
                condition=Q(
                    employer_percent__gte=0,
                    employer_percent__lte=100,
                    employee_percent__gte=0,
                    employee_percent__lte=100,
                ),
                name="contribution_rate_in_range",
            ),
            models.CheckConstraint(
                condition=Q(wage_cap__isnull=True) | Q(wage_cap__gt=0, on_minimum_wage=False),
                name="contribution_cap_on_pay_only",
            ),
            models.CheckConstraint(
                condition=Q(wage_floor__isnull=True) | Q(wage_floor__gt=0, on_minimum_wage=False),
                name="contribution_floor_on_pay_only",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.scheme} {self.province or 'all'} {self.starts_on}"


class GratuityRule(TenantOwnedModel):
    """How one country's end-of-service gratuity is worked out from a day on, with the law it is
    read from. It holds until a later rule for the same country replaces it. Payouts and payslips
    keep the figures they came to, so a change here never rewrites them."""

    class Wage(models.TextChoices):
        # The UAE counts the basic wage only (Article 51); Saudi Arabia the actual wage, basic
        # plus allowances (Labor Law Article 2).
        BASIC = "basic"
        FULL = "full"

    country = models.CharField(max_length=2)
    starts_on = models.DateField()
    first_years = models.DecimalField(max_digits=5, decimal_places=2)
    first_days = models.DecimalField(max_digits=6, decimal_places=2)
    later_days = models.DecimalField(max_digits=6, decimal_places=2)
    month_days = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    min_years = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cap_months = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    wage = models.CharField(max_length=5, choices=Wage.choices)
    # The UAE leaves out its own nationals: their end of service is a pension.
    excludes_nationals = models.BooleanField(default=False)
    # The UAE leaves unpaid days of absence out of the service (Article 51(4)).
    excludes_unpaid_days = models.BooleanField(default=False)
    # [{"years": "2", "share": "1/3", "after": false}, ...], lowest first; empty when resigning
    # changes nothing. Shares are fractions so a third stays exactly a third.
    resignation = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["country", "-starts_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "country", "starts_on"], name="uniq_gratuity_rule_start"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.country} {self.starts_on}"


class GratuityPayout(TenantOwnedModel):
    """The end-of-service gratuity paid to someone who left, once. It uses up the provision
    their payslips built up; any difference is booked to the expense."""

    class Reason(models.TextChoices):
        # Ended by the business, or the contract simply came to its end: the full award.
        ENDED = "ended"
        RESIGNED = "resigned"

    employee = models.OneToOneField(Employee, on_delete=models.PROTECT, related_name="gratuity")
    rule = models.ForeignKey(GratuityRule, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=10, choices=Reason.choices)
    service_days = models.PositiveIntegerField()
    wage = money_field()
    full = money_field()
    share = models.DecimalField(max_digits=7, decimal_places=6)
    amount = money_field()
    provision = money_field()
    paid_on = models.DateField()
    paid_from = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    entry = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="+")
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-paid_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0, provision__gte=0), name="gratuity_payout_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.amount}"

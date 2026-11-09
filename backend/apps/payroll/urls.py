from django.urls import path

from . import views

urlpatterns = [
    path("tax-tables/", views.TaxTableListView.as_view(), name="payroll-tax-tables"),
    path("tax-tables/fill/", views.TaxTableFillView.as_view(), name="payroll-tax-tables-fill"),
    path("tax-tables/<int:pk>/", views.TaxTableDetailView.as_view(), name="payroll-tax-table"),
    path("minimum-wages/", views.MinimumWageListView.as_view(), name="payroll-minimum-wages"),
    path(
        "minimum-wages/<int:pk>/",
        views.MinimumWageDetailView.as_view(),
        name="payroll-minimum-wage",
    ),
    path(
        "contribution-rates/",
        views.ContributionRateListView.as_view(),
        name="payroll-contribution-rates",
    ),
    path(
        "contribution-rates/<int:pk>/",
        views.ContributionRateDetailView.as_view(),
        name="payroll-contribution-rate",
    ),
    path(
        "contributions/fill/",
        views.ContributionsFillView.as_view(),
        name="payroll-contributions-fill",
    ),
    path("gratuity-rules/", views.GratuityRuleListView.as_view(), name="payroll-gratuity-rules"),
    path(
        "gratuity-rules/<int:pk>/",
        views.GratuityRuleDetailView.as_view(),
        name="payroll-gratuity-rule",
    ),
    path("gratuity-rules/fill/", views.GratuityFillView.as_view(), name="payroll-gratuity-fill"),
    path(
        "employees/<int:pk>/gratuity/",
        views.EmployeeGratuityView.as_view(),
        name="payroll-employee-gratuity",
    ),
    path(
        "employees/<int:pk>/gratuity/pay/",
        views.EmployeeGratuityPayView.as_view(),
        name="payroll-employee-gratuity-pay",
    ),
    path("runs/", views.PayrollRunListView.as_view(), name="payroll-runs"),
    path("runs/<int:pk>/", views.PayrollRunDetailView.as_view(), name="payroll-run"),
    path("runs/<int:pk>/post/", views.PayrollRunPostView.as_view(), name="payroll-run-post"),
    path("runs/<int:pk>/pay/", views.PayrollRunPayView.as_view(), name="payroll-run-pay"),
    path(
        "runs/<int:pk>/reverse/",
        views.PayrollRunReverseView.as_view(),
        name="payroll-run-reverse",
    ),
    path(
        "runs/<int:pk>/transfer-list/",
        views.TransferListView.as_view(),
        name="payroll-run-transfer-list",
    ),
    path("opening-pay/", views.OpeningPayListView.as_view(), name="payroll-opening-pay"),
    path(
        "opening-pay/<int:pk>/",
        views.OpeningPayDetailView.as_view(),
        name="payroll-opening-pay-detail",
    ),
    path("payslips/<int:pk>/pdf/", views.PayslipPdfView.as_view(), name="payroll-payslip-pdf"),
]

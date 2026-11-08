from django.urls import path

from . import views

urlpatterns = [
    path("tax-tables/", views.TaxTableListView.as_view(), name="payroll-tax-tables"),
    path("tax-tables/fill/", views.TaxTableFillView.as_view(), name="payroll-tax-tables-fill"),
    path("tax-tables/<int:pk>/", views.TaxTableDetailView.as_view(), name="payroll-tax-table"),
    path("runs/", views.PayrollRunListView.as_view(), name="payroll-runs"),
    path("runs/<int:pk>/", views.PayrollRunDetailView.as_view(), name="payroll-run"),
    path("runs/<int:pk>/post/", views.PayrollRunPostView.as_view(), name="payroll-run-post"),
    path("payslips/<int:pk>/pdf/", views.PayslipPdfView.as_view(), name="payroll-payslip-pdf"),
]

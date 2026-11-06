from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="report-dashboard"),
    path("profit-loss/", views.ProfitLossView.as_view(), name="report-profit-loss"),
    path("balance-sheet/", views.BalanceSheetView.as_view(), name="report-balance-sheet"),
    path("cash-flow/", views.CashFlowView.as_view(), name="report-cash-flow"),
    path("sales-tax/", views.SalesTaxView.as_view(), name="report-sales-tax"),
]

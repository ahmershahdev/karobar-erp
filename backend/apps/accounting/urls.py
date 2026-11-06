from django.urls import path

from . import views

urlpatterns = [
    path("accounts/", views.AccountListView.as_view(), name="account-list"),
    path("accounts/<int:pk>/", views.AccountDetailView.as_view(), name="account-detail"),
    path("accounts/<int:pk>/ledger/", views.LedgerView.as_view(), name="account-ledger"),
    path("tax-rates/", views.TaxRateListView.as_view(), name="tax-rate-list"),
    path("tax-rates/<int:pk>/", views.TaxRateDetailView.as_view(), name="tax-rate-detail"),
    path("fiscal-years/", views.FiscalYearListView.as_view(), name="fiscal-year-list"),
    path("periods/<int:pk>/", views.PeriodDetailView.as_view(), name="period-detail"),
    path("entries/", views.EntryListView.as_view(), name="entry-list"),
    path("entries/<int:pk>/", views.EntryDetailView.as_view(), name="entry-detail"),
    path("entries/<int:pk>/post/", views.EntryPostView.as_view(), name="entry-post"),
    path("entries/<int:pk>/reverse/", views.EntryReverseView.as_view(), name="entry-reverse"),
    path("reports/trial-balance/", views.TrialBalanceView.as_view(), name="trial-balance"),
]

from django.urls import path

from . import views

urlpatterns = [
    path("customers/", views.CustomerListView.as_view(), name="customer-list"),
    path("customers/<int:pk>/", views.CustomerDetailView.as_view(), name="customer-detail"),
    path(
        "customers/<int:pk>/statement/",
        views.CustomerStatementView.as_view(),
        name="customer-statement",
    ),
    path("ageing/", views.ReceivablesAgeingView.as_view(), name="receivables-ageing"),
    path("tax-rates/", views.SalesTaxRateListView.as_view(), name="sales-tax-rates"),
    path("invoices/<int:pk>/pdf/", views.InvoicePdfView.as_view(), name="invoice-pdf"),
    path("invoices/<int:pk>/share/", views.InvoiceShareView.as_view(), name="invoice-share"),
    path("receipts/<int:pk>/pdf/", views.ReceiptPdfView.as_view(), name="sales-receipt-pdf"),
    path("orders/", views.OrderListView.as_view(), name="so-list"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="so-detail"),
    path("orders/<int:pk>/quote/", views.OrderQuoteView.as_view(), name="so-quote"),
    path("orders/<int:pk>/confirm/", views.OrderConfirmView.as_view(), name="so-confirm"),
    path("orders/<int:pk>/close/", views.OrderCloseView.as_view(), name="so-close"),
    path("orders/<int:pk>/invoice/", views.OrderInvoiceView.as_view(), name="so-invoice"),
    path("bill-settings/", views.BillSettingsView.as_view(), name="bill-settings"),
    path("bill-settings/logo/", views.BillImageView.as_view(kind="logo"), name="bill-logo"),
    path(
        "bill-settings/signature/",
        views.BillImageView.as_view(kind="signature"),
        name="bill-signature",
    ),
    path("invoices/", views.InvoiceListView.as_view(), name="invoice-list"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice-detail"),
    path("invoices/<int:pk>/post/", views.InvoicePostView.as_view(), name="invoice-post"),
    path("invoices/<int:pk>/credit/", views.InvoiceCreditView.as_view(), name="invoice-credit"),
    path("receipts/", views.ReceiptListView.as_view(), name="sales-receipt-list"),
    path("receipts/<int:pk>/", views.ReceiptDetailView.as_view(), name="sales-receipt-detail"),
    path("receipts/<int:pk>/post/", views.ReceiptPostView.as_view(), name="sales-receipt-post"),
    path("credit-notes/", views.CreditListView.as_view(), name="credit-list"),
    path("credit-notes/<int:pk>/", views.CreditDetailView.as_view(), name="credit-detail"),
    path("credit-notes/<int:pk>/post/", views.CreditPostView.as_view(), name="credit-post"),
]

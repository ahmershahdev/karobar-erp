from django.urls import path

from . import views

urlpatterns = [
    path("suppliers/", views.SupplierListView.as_view(), name="supplier-list"),
    path("suppliers/<int:pk>/", views.SupplierDetailView.as_view(), name="supplier-detail"),
    path("orders/", views.OrderListView.as_view(), name="po-list"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="po-detail"),
    path("orders/<int:pk>/confirm/", views.OrderConfirmView.as_view(), name="po-confirm"),
    path("orders/<int:pk>/close/", views.OrderCloseView.as_view(), name="po-close"),
    path("orders/<int:pk>/receive/", views.OrderReceiveView.as_view(), name="po-receive"),
    path("receipts/", views.ReceiptListView.as_view(), name="receipt-list"),
    path("receipts/<int:pk>/", views.ReceiptDetailView.as_view(), name="receipt-detail"),
    path("receipts/<int:pk>/post/", views.ReceiptPostView.as_view(), name="receipt-post"),
    path("receipts/<int:pk>/bill/", views.ReceiptBillView.as_view(), name="receipt-bill"),
    path("bills/", views.BillListView.as_view(), name="bill-list"),
    path("bills/<int:pk>/", views.BillDetailView.as_view(), name="bill-detail"),
    path("bills/<int:pk>/post/", views.BillPostView.as_view(), name="bill-post"),
    path("payments/", views.PaymentListView.as_view(), name="payment-list"),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("payments/<int:pk>/post/", views.PaymentPostView.as_view(), name="payment-post"),
]

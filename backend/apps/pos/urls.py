from django.urls import path

from . import views

urlpatterns = [
    path("sessions/", views.SessionListView.as_view(), name="pos-sessions"),
    path("sessions/<int:pk>/", views.SessionDetailView.as_view(), name="pos-session"),
    path("sessions/<int:pk>/sale/", views.SaleView.as_view(), name="pos-sale"),
    path("sessions/<int:pk>/close/", views.CloseTillView.as_view(), name="pos-close"),
    path("sales/<int:pk>/receipt/", views.SaleReceiptView.as_view(), name="pos-receipt"),
    path("products/", views.ProductSearchView.as_view(), name="pos-products"),
    path("warehouses/", views.PosWarehouseListView.as_view(), name="pos-warehouses"),
    path("tax-rates/", views.PosTaxRateListView.as_view(), name="pos-tax-rates"),
]

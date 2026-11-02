from django.urls import path

from . import views

urlpatterns = [
    path("units/", views.UnitListView.as_view(), name="unit-list"),
    path("units/<int:pk>/", views.UnitDetailView.as_view(), name="unit-detail"),
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("categories/<int:pk>/", views.CategoryDetailView.as_view(), name="category-detail"),
    path("warehouses/", views.WarehouseListView.as_view(), name="warehouse-list"),
    path("warehouses/<int:pk>/", views.WarehouseDetailView.as_view(), name="warehouse-detail"),
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product-detail"),
    path("products/<int:pk>/moves/", views.ProductMovesView.as_view(), name="product-moves"),
    path("batches/", views.BatchListView.as_view(), name="batch-list"),
    path("stock-levels/", views.StockLevelListView.as_view(), name="stock-level-list"),
    path("stock-value/", views.StockValueView.as_view(), name="stock-value"),
    path("stock-entries/", views.StockEntryListView.as_view(), name="stock-entry-list"),
    path(
        "stock-entries/<int:pk>/", views.StockEntryDetailView.as_view(), name="stock-entry-detail"
    ),
    path(
        "stock-entries/<int:pk>/post/", views.StockEntryPostView.as_view(), name="stock-entry-post"
    ),
    path("alerts/", views.AlertsView.as_view(), name="stock-alerts"),
]

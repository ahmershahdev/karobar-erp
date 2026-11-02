from django.urls import path

from . import views

urlpatterns = [
    path("tenants/", views.MyTenantsView.as_view(), name="my-tenants"),
    path("audit/", views.AuditEventListView.as_view(), name="audit-list"),
    path("audit/<int:pk>/", views.AuditEventDetailView.as_view(), name="audit-detail"),
]

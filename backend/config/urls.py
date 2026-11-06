from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from apps.platform.views import HealthView

urlpatterns = [
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/", include("apps.tenancy.urls")),
    path("api/accounting/", include("apps.accounting.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
    path("api/purchasing/", include("apps.purchasing.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(settings.ADMIN_URL, admin.site.urls),
]

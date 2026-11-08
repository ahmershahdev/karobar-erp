from django.urls import path

from . import views

urlpatterns = [
    path("departments/", views.DepartmentListView.as_view(), name="hr-departments"),
    path("departments/<int:pk>/", views.DepartmentDetailView.as_view(), name="hr-department"),
    path("salary-structures/", views.SalaryStructureListView.as_view(), name="hr-structures"),
    path(
        "salary-structures/<int:pk>/",
        views.SalaryStructureDetailView.as_view(),
        name="hr-structure",
    ),
    path(
        "salary-structures/<int:pk>/preview/",
        views.SalaryPreviewView.as_view(),
        name="hr-structure-preview",
    ),
    path("employees/", views.EmployeeListView.as_view(), name="hr-employees"),
    path("employees/<int:pk>/", views.EmployeeDetailView.as_view(), name="hr-employee"),
    path("contracts/", views.ContractListView.as_view(), name="hr-contracts"),
    path("contracts/<int:pk>/", views.ContractDetailView.as_view(), name="hr-contract"),
]

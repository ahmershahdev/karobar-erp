from django.urls import path

from . import time_off_api as time_off
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
    path("settings/", time_off.HrSettingsView.as_view(), name="hr-settings"),
    path("holidays/", time_off.HolidayListView.as_view(), name="hr-holidays"),
    path("holidays/fill/", time_off.HolidayFillView.as_view(), name="hr-holidays-fill"),
    path("holidays/<int:pk>/", time_off.HolidayDetailView.as_view(), name="hr-holiday"),
    path("leave-types/", time_off.LeaveTypeListView.as_view(), name="hr-leave-types"),
    path("leave-types/<int:pk>/", time_off.LeaveTypeDetailView.as_view(), name="hr-leave-type"),
    path("leave/", time_off.LeaveListView.as_view(), name="hr-leave"),
    path("leave/balances/", time_off.LeaveBalanceView.as_view(), name="hr-leave-balances"),
    path("leave/<int:pk>/", time_off.LeaveDetailView.as_view(), name="hr-leave-detail"),
    path(
        "leave/<int:pk>/approve/",
        time_off.LeaveDecisionView.as_view(approve=True),
        name="hr-leave-approve",
    ),
    path(
        "leave/<int:pk>/reject/",
        time_off.LeaveDecisionView.as_view(approve=False),
        name="hr-leave-reject",
    ),
    path("attendance/", time_off.AttendanceView.as_view(), name="hr-attendance"),
]

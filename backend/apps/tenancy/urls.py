from django.urls import path

from . import views

urlpatterns = [
    path("tenants/", views.MyTenantsView.as_view(), name="my-tenants"),
    path("automation/", views.AutomationView.as_view(), name="automation"),
    path("roles/", views.RoleListView.as_view(), name="role-list"),
    path("roles/<int:pk>/", views.RoleDetailView.as_view(), name="role-detail"),
    path("members/", views.MemberListView.as_view(), name="member-list"),
    path("members/<int:pk>/", views.MemberDetailView.as_view(), name="member-detail"),
    path("members/<int:pk>/make-owner/", views.MemberOwnerView.as_view(), name="member-owner"),
    path("invitations/", views.InvitationListView.as_view(), name="invitation-list"),
    path("invitations/<int:pk>/", views.InvitationDetailView.as_view(), name="invitation-detail"),
    path("invitations/accept/", views.AcceptInvitationView.as_view(), name="invitation-accept"),
    path("audit/", views.AuditEventListView.as_view(), name="audit-list"),
    path("audit/<int:pk>/", views.AuditEventDetailView.as_view(), name="audit-detail"),
]

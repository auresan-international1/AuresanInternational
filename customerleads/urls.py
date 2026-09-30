from django.urls import path
from . import views

urlpatterns = [
    # Main entry point
    path('', views.CustomLoginView.as_view(), name='login_home'),

    # Authentication
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),

    # Dashboard redirect logic
    path('dashboard-redirect/', views.DashboardRedirectView.as_view(), name='dashboard_redirect'),
    path('dashboard-redirect/', views.DashboardRedirectView.as_view(), name='dashboard'),

    # Admin Dashboard
    path('administrator/dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),

    # Staff Dashboard (and its partials)
    path('staff/dashboard/', views.operator_dashboard, name='staff_dashboard'),
    path('staff/create-lead/', views.create_lead_view, name='create_lead'),
    path('staff/my-conversations/', views.my_conversations_view, name='my_conversations'),
    path('staff/charts/', views.staff_charts_view, name='staff_charts'),
    path('staff/call-requests/', views.call_requests_view, name='call_requests'),
    path('staff/update-callback-status/<str:cb_id>/', views.update_callback_status, name='update_callback_status'),
    path('staff/convert-callback-to-lead/<str:cb_id>/', views.convert_callback_to_lead, name='convert_callback_to_lead'),
    path('staff/start-conversation/', views.start_conversation_view, name='start_conversation'),
    path('leads/<str:lead_id>/update-call-outcome/', views.update_lead_call_outcome, name='update_lead_call_outcome'),
    path('leads/<str:lead_id>/confirm-order-form/', views.get_confirm_order_form, name='get_confirm_order_form'),
    path('leads/<str:lead_id>/confirm-order/', views.confirm_website_order, name='confirm_website_order'),
    path('leads/<str:lead_id>/send-sms/', views.send_sms_view, name='send_sms'),
    path('leads/<str:lead_id>/send-email/', views.send_email_view, name='send_email'),

    # Automated Dialer
    path('staff/start-auto-dial/', views.start_auto_dial, name='start_auto_dial'),
    path('leads/<str:lead_id>/call/', views.call_lead, name='call_lead'),

    # Generic Lead Management
    path('leads/', views.LeadListView.as_view(), name='leads'),
    path('leads/create/', views.LeadCreateView.as_view(), name='lead_create'),
    path('leads/<str:pk>/', views.LeadDetailView.as_view(), name='lead_detail'),
    path('leads/<str:pk>/update/', views.LeadUpdateView.as_view(), name='lead_update'),
    path('leads/<str:pk>/delete/', views.LeadDeleteView.as_view(), name='lead_delete'),
    path('leads/<str:lead_id>/convert/', views.convert_lead_to_client, name='convert_lead_to_client'),

    # Deliveries
    path('deliveries/', views.DeliveryListView.as_view(), name='deliveries'),
    path('deliveries/create/', views.DeliveryCreateView.as_view(), name='delivery_create'),
    path('deliveries/<str:pk>/', views.DeliveryDetailView.as_view(), name='delivery_detail'),
    path('deliveries/<str:pk>/update/', views.DeliveryUpdateView.as_view(), name='delivery_update'),
    path('deliveries/<str:delivery_id>/assign/', views.assign_delivery_person, name='assign_delivery_person'),
    path('deliveries/<str:delivery_id>/status/', views.update_delivery_status, name='update_delivery_status'),

    # Deal Management
    path('deals/create/', views.DealCreateView.as_view(), name='deal_create'),
    path('deals/<str:pk>/', views.DealDetailView.as_view(), name='deal_detail'),
    path('deals/<str:pk>/update/', views.DealUpdateView.as_view(), name='deal_update'),

    # User Management (Django ORM → keep <int:pk>)
    path('users/', views.UserManagementView.as_view(), name='user_management'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/update/', views.UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),
    path('users/<int:pk>/activate/', views.UserActivateView.as_view(), name='user_activate'),
    path('users/<int:pk>/deactivate/', views.UserDeactivateView.as_view(), name='user_deactivate'),

    # Sales Pipeline
    path('sales-pipeline/', views.SalesPipelineView.as_view(), name='sales_pipeline'),

    # Profile
    path('profile/', views.UserProfileView.as_view(), name='profile'),

    # Tasks
    path('tasks/', views.TaskListView.as_view(), name='tasks'),
    path('tasks/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('tasks/<str:pk>/', views.TaskDetailView.as_view(), name='task_detail'),
    path('tasks/<str:pk>/update/', views.TaskUpdateView.as_view(), name='task_update'),
    path('tasks/<str:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    path('tasks/<str:task_id>/complete/', views.mark_task_complete, name='task_complete'),

    # Interactions
    path('interactions/', views.InteractionListView.as_view(), name='interactions'),
    path('interactions/create/', views.InteractionCreateView.as_view(), name='interaction_create'),

    # Analytics & Reports
    path('analytics/', views.AnalyticsView.as_view(), name='analytics'),
    path('reports/', views.ReportsView.as_view(), name='reports'),

    # Client Management
    path('clients/', views.ClientListView.as_view(), name='clients'),
    path('clients/<str:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('clients/<str:pk>/update/', views.ClientUpdateView.as_view(), name='client_update'),
    path('clients/<str:pk>/delete/', views.ClientDetailView.as_view(), name='client_delete'),

    # System & Features
    path('activity-logs/', views.ActivityLogView.as_view(), name='activity_logs'),
    path('email-notifications/', views.EmailNotificationsView.as_view(), name='email_notifications'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
    path('api-management/', views.APIManagementView.as_view(), name='api_management'),
    path('help-support/', views.HelpSupportView.as_view(), name='help_support'),

    # Top Navigation
    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('quick-add/', views.QuickAddView.as_view(), name='quick_add'),
]
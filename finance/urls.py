from django.urls import path
from django.contrib.auth import views as auth
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.SecureLoginView.as_view(), name='login'),
    path('signup/', views.signup, name='signup'),
    path('logout/', auth.LogoutView.as_view(), name='logout'),
    path('password/reset/', auth.PasswordResetView.as_view(template_name='registration/reset.html',
         email_template_name='registration/reset_email.txt', subject_template_name='registration/reset_subject.txt'), name='password_reset'),
    path('password/sent/', auth.PasswordResetDoneView.as_view(template_name='registration/reset_done.html'), name='password_reset_done'),
    path('password/<uidb64>/<token>/', auth.PasswordResetConfirmView.as_view(template_name='registration/reset_confirm.html'), name='password_reset_confirm'),
    path('password/done/', auth.PasswordResetCompleteView.as_view(template_name='registration/reset_complete.html'), name='password_reset_complete'),
    path('accounts/', views.accounts, name='accounts'),
    path('accounts/new/', views.account_form, name='account_create'),
    path('accounts/<int:pk>/edit/', views.account_form, name='account_edit'),
    path('accounts/<int:pk>/delete/', views.delete_item, {'model': 'account'}, name='account_delete'),
    path('operations/', views.operations, name='operations'),
    path('operations/new/', views.operation_form, name='operation_create'),
    path('operations/<int:pk>/edit/', views.operation_form, name='operation_edit'),
    path('operations/<int:pk>/delete/', views.delete_item, {'model': 'operation'}, name='operation_delete'),
    path('transfer/', views.transfer, name='transfer'),
    path('analytics/', views.analytics, name='analytics'),
    path('categories/', views.categories, name='categories'),
    path('categories/<int:pk>/delete/', views.delete_item, {'model': 'category'}, name='category_delete'),
    path('import/', views.import_upload, name='import_upload'),
    path('import/<uuid:pk>/', views.import_preview, name='import_preview'),
    path('import/<uuid:pk>/delete/', views.delete_item, {'model': 'batch'}, name='batch_delete'),
    path('samples/<str:extension>/', views.sample, name='sample'),
    path('demo/', views.demo, name='demo'),
]

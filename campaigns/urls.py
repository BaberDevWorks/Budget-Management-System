"""
URL patterns for the campaigns app.
"""
from django.urls import path
from typing import List
from django.urls import URLPattern

from . import views

app_name = 'campaigns'

urlpatterns: List[URLPattern] = [
    path('', views.dashboard, name='dashboard'),
    path('brands/', views.brand_list, name='brand_list'),
    path('brands/<int:brand_id>/', views.brand_detail, name='brand_detail'),
    path('campaigns/', views.campaign_list, name='campaign_list'),
    path('campaigns/<int:campaign_id>/', views.campaign_detail, name='campaign_detail'),
    path('api/record-spend/', views.record_spend_api, name='record_spend_api'),
    path('api/budget-status/', views.budget_status_api, name='budget_status_api'),
    path('api/dayparting-status/', views.dayparting_status_api, name='dayparting_status_api'),
] 
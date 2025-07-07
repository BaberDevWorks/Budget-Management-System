"""
Django admin interface for the campaigns app.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.http import HttpRequest
from django.db.models import QuerySet
from typing import Any, List, Optional, Tuple, TYPE_CHECKING
from decimal import Decimal

from .models import Brand, Campaign, Spend, DaypartingSchedule

if TYPE_CHECKING:
    from django.contrib.admin import ModelAdmin
    from django.contrib.admin import TabularInline
    BrandAdminBase = ModelAdmin[Brand]
    CampaignAdminBase = ModelAdmin[Campaign]
    DaypartingScheduleAdminBase = ModelAdmin[DaypartingSchedule]
    SpendAdminBase = ModelAdmin[Spend]
    DaypartingScheduleInlineBase = TabularInline[DaypartingSchedule, Campaign]
else:
    BrandAdminBase = admin.ModelAdmin
    CampaignAdminBase = admin.ModelAdmin
    DaypartingScheduleAdminBase = admin.ModelAdmin
    SpendAdminBase = admin.ModelAdmin
    DaypartingScheduleInlineBase = admin.TabularInline


@admin.register(Brand)
class BrandAdmin(BrandAdminBase):
    """Admin interface for Brand model."""
    
    list_display = [
        'name', 'daily_budget', 'daily_spend', 'daily_budget_status',
        'monthly_budget', 'monthly_spend', 'monthly_budget_status',
        'is_active', 'campaigns_count', 'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['name']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'is_active')
        }),
        ('Budget Settings', {
            'fields': ('daily_budget', 'monthly_budget')
        }),
        ('Current Spend', {
            'fields': ('daily_spend', 'monthly_spend'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    @admin.display(description='Daily Status')
    def daily_budget_status(self, obj: Brand) -> str:
        """Display daily budget status with color coding."""
        if obj.is_daily_budget_exceeded():
            return format_html(
                '<span style="color: red;">⚠️ Over Budget</span>'
            )
        elif obj.daily_spend >= obj.daily_budget * Decimal('0.8'):
            return format_html(
                '<span style="color: orange;">⚠️ Near Limit</span>'
            )
        else:
            return format_html(
                '<span style="color: green;">✅ Within Budget</span>'
            )
    
    @admin.display(description='Monthly Status')
    def monthly_budget_status(self, obj: Brand) -> str:
        """Display monthly budget status with color coding."""
        if obj.is_monthly_budget_exceeded():
            return format_html(
                '<span style="color: red;">⚠️ Over Budget</span>'
            )
        elif obj.monthly_spend >= obj.monthly_budget * Decimal('0.8'):
            return format_html(
                '<span style="color: orange;">⚠️ Near Limit</span>'
            )
        else:
            return format_html(
                '<span style="color: green;">✅ Within Budget</span>'
            )
    
    @admin.display(description='Campaigns')
    def campaigns_count(self, obj: Brand) -> int:
        """Display number of campaigns for this brand."""
        return obj.campaigns.count()
    
    actions = ['reset_daily_spend', 'reset_monthly_spend', 'reset_both_spends']
    
    @admin.action(description='Reset daily spend')
    def reset_daily_spend(self, request: HttpRequest, queryset: QuerySet[Brand]) -> None:
        """Reset daily spend for selected brands."""
        count = 0
        for brand in queryset:
            brand.reset_daily_spend()
            count += 1
        self.message_user(request, f'Reset daily spend for {count} brands.')
    
    @admin.action(description='Reset monthly spend')
    def reset_monthly_spend(self, request: HttpRequest, queryset: QuerySet[Brand]) -> None:
        """Reset monthly spend for selected brands."""
        count = 0
        for brand in queryset:
            brand.reset_monthly_spend()
            count += 1
        self.message_user(request, f'Reset monthly spend for {count} brands.')
    
    @admin.action(description='Reset both spends')
    def reset_both_spends(self, request: HttpRequest, queryset: QuerySet[Brand]) -> None:
        """Reset both daily and monthly spend for selected brands."""
        count = 0
        for brand in queryset:
            brand.reset_daily_spend()
            brand.reset_monthly_spend()
            count += 1
        self.message_user(request, f'Reset both spends for {count} brands.')


@admin.register(Campaign)
class CampaignAdmin(CampaignAdminBase):
    """Admin interface for Campaign model."""
    
    list_display = [
        'name', 'brand', 'is_active', 'status_indicators',
        'dayparting_schedules_count', 'total_spend_today',
        'created_at'
    ]
    list_filter = [
        'is_active', 'is_paused_by_budget', 'is_paused_by_dayparting',
        'brand', 'created_at'
    ]
    search_fields = ['name', 'brand__name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['brand__name', 'name']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('brand', 'name')
        }),
        ('Status', {
            'fields': ('is_active', 'is_paused_by_budget', 'is_paused_by_dayparting')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    @admin.display(description='Status')
    def status_indicators(self, obj: Campaign) -> str:
        """Display status indicators for the campaign."""
        indicators = []
        
        if obj.is_active:
            indicators.append('<span style="color: green;">🟢 Active</span>')
        else:
            indicators.append('<span style="color: red;">🔴 Inactive</span>')
        
        if obj.is_paused_by_budget:
            indicators.append('<span style="color: red;">💰 Budget Paused</span>')
        
        if obj.is_paused_by_dayparting:
            indicators.append('<span style="color: orange;">⏰ Dayparting Paused</span>')
        
        return format_html(' | '.join(indicators))
    
    @admin.display(description='Schedules')
    def dayparting_schedules_count(self, obj: Campaign) -> int:
        """Display number of dayparting schedules."""
        return obj.dayparting_schedules.count()
    
    @admin.display(description="Today's Spend")
    def total_spend_today(self, obj: Campaign) -> str:
        """Display total spend for today."""
        return f"${obj.total_spend_today()}"
    
    actions = ['update_dayparting_status', 'activate_campaigns', 'deactivate_campaigns']
    
    @admin.action(description='Update dayparting status')
    def update_dayparting_status(self, request: HttpRequest, queryset: QuerySet[Campaign]) -> None:
        """Update dayparting status for selected campaigns."""
        count = 0
        for campaign in queryset:
            campaign.update_dayparting_status()
            count += 1
        self.message_user(request, f'Updated dayparting status for {count} campaigns.')
    
    @admin.action(description='Activate campaigns')
    def activate_campaigns(self, request: HttpRequest, queryset: QuerySet[Campaign]) -> None:
        """Activate selected campaigns (if not paused by budget/dayparting)."""
        count = 0
        for campaign in queryset:
            if not campaign.is_paused_by_budget and campaign.is_in_dayparting_window():
                campaign.is_active = True
                campaign.save()
                count += 1
        self.message_user(request, f'Activated {count} campaigns.')
    
    @admin.action(description='Deactivate campaigns')
    def deactivate_campaigns(self, request: HttpRequest, queryset: QuerySet[Campaign]) -> None:
        """Deactivate selected campaigns."""
        count = 0
        for campaign in queryset:
            campaign.is_active = False
            campaign.save()
            count += 1
        self.message_user(request, f'Deactivated {count} campaigns.')


class DaypartingScheduleInline(DaypartingScheduleInlineBase):
    """Inline admin for DaypartingSchedule."""
    model = DaypartingSchedule
    extra = 1
    fields = ['day_of_week', 'start_time', 'end_time', 'is_active']


@admin.register(DaypartingSchedule)
class DaypartingScheduleAdmin(DaypartingScheduleAdminBase):
    """Admin interface for DaypartingSchedule model."""
    
    list_display = [
        'campaign', 'day_of_week_display', 'start_time', 'end_time',
        'is_active', 'is_active_now', 'created_at'
    ]
    list_filter = ['day_of_week', 'is_active', 'created_at']
    search_fields = ['campaign__name', 'campaign__brand__name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['campaign__brand__name', 'campaign__name', 'day_of_week', 'start_time']
    
    fieldsets = (
        ('Schedule Information', {
            'fields': ('campaign', 'day_of_week', 'start_time', 'end_time')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    @admin.display(description='Day of Week')
    def day_of_week_display(self, obj: DaypartingSchedule) -> str:
        """Display day of week name."""
        return str(obj.get_day_of_week_display())
    
    @admin.display(description='Active Now')
    def is_active_now(self, obj: DaypartingSchedule) -> str:
        """Display if schedule is currently active."""
        if obj.is_active_now():
            return format_html('<span style="color: green;">✅ Active</span>')
        else:
            return format_html('<span style="color: red;">❌ Inactive</span>')


@admin.register(Spend)
class SpendAdmin(SpendAdminBase):
    """Admin interface for Spend model."""
    
    list_display = [
        'campaign', 'brand_name', 'amount', 'spent_at', 'created_at'
    ]
    list_filter = ['spent_at', 'created_at', 'campaign__brand']
    search_fields = ['campaign__name', 'campaign__brand__name']
    readonly_fields = ['created_at']
    ordering = ['-spent_at']
    date_hierarchy = 'spent_at'
    
    fieldsets = (
        ('Spend Information', {
            'fields': ('campaign', 'amount', 'spent_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    @admin.display(description='Brand')
    def brand_name(self, obj: Spend) -> str:
        """Display brand name for the spend."""
        return str(obj.campaign.brand.name)
    
    def get_queryset(self, request: HttpRequest) -> QuerySet[Spend]:
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related('campaign__brand')

# Add inline to Campaign admin
CampaignAdmin.inlines = [DaypartingScheduleInline]

# Customize admin site
admin.site.site_header = "Budget Management System"
admin.site.site_title = "Budget Management"
admin.site.index_title = "Campaign Budget Management" 
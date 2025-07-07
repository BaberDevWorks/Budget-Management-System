"""
Service classes for budget management and dayparting logic.
"""
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple, cast, TypedDict, Literal
import logging

from .models import Brand, Campaign, Spend, DaypartingSchedule

logger = logging.getLogger(__name__)


# TypedDict definitions for return types
class BudgetCheckResult(TypedDict):
    brands_checked: int
    brands_over_daily_budget: int
    brands_over_monthly_budget: int
    campaigns_paused: int
    campaigns_reactivated: int
    timestamp: str


class BrandBudgetResult(TypedDict):
    brand_id: int
    brand_name: str
    daily_budget: str
    daily_spend: str
    monthly_budget: str
    monthly_spend: str
    daily_exceeded: bool
    monthly_exceeded: bool
    remaining_daily: str
    remaining_monthly: str
    timestamp: str
    campaigns_paused: Optional[int]
    campaigns_reactivated: Optional[int]


class BrandDetail(TypedDict):
    id: int
    name: str
    daily_spend: str
    daily_budget: str
    monthly_spend: str
    monthly_budget: str
    daily_exceeded: bool
    monthly_exceeded: bool
    active_campaigns: int
    paused_campaigns: int


class BudgetSummary(TypedDict):
    total_brands: int
    brands_over_daily_budget: int
    brands_over_monthly_budget: int
    total_daily_spend: str
    total_monthly_spend: str
    total_daily_budget: str
    total_monthly_budget: str
    brand_details: List[BrandDetail]
    timestamp: str


class DaypartingUpdateResult(TypedDict):
    campaigns_checked: int
    campaigns_activated: int
    campaigns_deactivated: int
    campaigns_unchanged: int
    timestamp: str


class CampaignDaypartingResult(TypedDict):
    campaign_id: int
    campaign_name: str
    brand_name: str
    old_status: bool
    new_status: bool
    old_dayparting_pause: bool
    new_dayparting_pause: bool
    is_in_dayparting_window: bool
    timestamp: str


class CampaignDetail(TypedDict):
    id: int
    name: str
    brand_name: str
    is_active: bool
    is_paused_by_dayparting: bool
    is_in_dayparting_window: bool
    schedule_count: int
    active_schedules: int


class DaypartingSummary(TypedDict):
    total_campaigns: int
    campaigns_in_dayparting_window: int
    campaigns_paused_by_dayparting: int
    campaigns_with_schedules: int
    campaigns_without_schedules: int
    total_schedules: int
    active_schedules: int
    campaign_details: List[CampaignDetail]
    timestamp: str


class ScheduleValidationResult(TypedDict):
    valid: bool
    error: Optional[str]
    campaign_id: Optional[int]
    campaign_name: Optional[str]
    day_of_week: Optional[int]
    start_time: Optional[str]
    end_time: Optional[str]


class BudgetService:
    """
    Service class for handling budget-related operations.
    """
    
    def __init__(self) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def check_all_budgets(self) -> BudgetCheckResult:
        """
        Check budget limits for all brands and pause campaigns if needed.
        Returns a summary of actions taken.
        """
        self.logger.info("Checking budget limits for all brands")
        
        brands_checked = 0
        brands_over_daily = 0
        brands_over_monthly = 0
        campaigns_paused = 0
        campaigns_reactivated = 0
        
        try:
            brands = Brand.objects.filter(is_active=True)
            
            for brand in brands:
                brands_checked += 1
                
                # Check if brand is over budget
                daily_exceeded = brand.is_daily_budget_exceeded()
                monthly_exceeded = brand.is_monthly_budget_exceeded()
                
                if daily_exceeded or monthly_exceeded:
                    # Pause all campaigns for this brand
                    paused_count = brand.pause_all_campaigns()
                    campaigns_paused += paused_count
                    
                    if daily_exceeded:
                        brands_over_daily += 1
                        self.logger.warning(f"Brand {brand.name} exceeded daily budget: ${brand.daily_spend}/${brand.daily_budget}")
                    
                    if monthly_exceeded:
                        brands_over_monthly += 1
                        self.logger.warning(f"Brand {brand.name} exceeded monthly budget: ${brand.monthly_spend}/${brand.monthly_budget}")
                
                else:
                    # Brand is within budget, reactivate campaigns if they were paused by budget
                    reactivated_count = brand.reactivate_campaigns()
                    campaigns_reactivated += reactivated_count
                    
                    if reactivated_count > 0:
                        self.logger.info(f"Reactivated {reactivated_count} campaigns for brand {brand.name}")
            
            results: BudgetCheckResult = {
                'brands_checked': brands_checked,
                'brands_over_daily_budget': brands_over_daily,
                'brands_over_monthly_budget': brands_over_monthly,
                'campaigns_paused': campaigns_paused,
                'campaigns_reactivated': campaigns_reactivated,
                'timestamp': timezone.now().isoformat()
            }
            
            self.logger.info(f"Budget check completed: {results}")
            return results
            
        except Exception as exc:
            self.logger.error(f"Error in budget check: {exc}")
            raise
    
    def check_brand_budget(self, brand_id: int) -> BrandBudgetResult:
        """
        Check budget limits for a specific brand.
        """
        try:
            brand = Brand.objects.get(id=brand_id)
        except Brand.DoesNotExist:
            raise ValueError(f"Brand {brand_id} not found")
        
        daily_exceeded = brand.is_daily_budget_exceeded()
        monthly_exceeded = brand.is_monthly_budget_exceeded()
        
        results: BrandBudgetResult = {
            'brand_id': brand_id,
            'brand_name': brand.name,
            'daily_budget': str(brand.daily_budget),
            'daily_spend': str(brand.daily_spend),
            'monthly_budget': str(brand.monthly_budget),
            'monthly_spend': str(brand.monthly_spend),
            'daily_exceeded': daily_exceeded,
            'monthly_exceeded': monthly_exceeded,
            'remaining_daily': str(brand.remaining_daily_budget()),
            'remaining_monthly': str(brand.remaining_monthly_budget()),
            'timestamp': timezone.now().isoformat(),
            'campaigns_paused': None,
            'campaigns_reactivated': None
        }
        
        if daily_exceeded or monthly_exceeded:
            campaigns_paused = brand.pause_all_campaigns()
            results['campaigns_paused'] = campaigns_paused
            self.logger.warning(f"Budget exceeded for brand {brand.name}, paused {campaigns_paused} campaigns")
        else:
            campaigns_reactivated = brand.reactivate_campaigns()
            results['campaigns_reactivated'] = campaigns_reactivated
            if campaigns_reactivated > 0:
                self.logger.info(f"Reactivated {campaigns_reactivated} campaigns for brand {brand.name}")
        
        return results
    
    def get_budget_summary(self) -> BudgetSummary:
        """
        Get a summary of budget status for all brands.
        """
        brands = Brand.objects.filter(is_active=True)
        
        brands_over_daily_budget = 0
        brands_over_monthly_budget = 0
        total_daily_spend = Decimal('0.00')
        total_monthly_spend = Decimal('0.00')
        total_daily_budget = Decimal('0.00')
        total_monthly_budget = Decimal('0.00')
        brand_details: List[BrandDetail] = []
        
        for brand in brands:
            if brand.is_daily_budget_exceeded():
                brands_over_daily_budget += 1
            
            if brand.is_monthly_budget_exceeded():
                brands_over_monthly_budget += 1
            
            # Fix arithmetic operations with proper type casting
            total_daily_spend += brand.daily_spend
            total_monthly_spend += brand.monthly_spend
            total_daily_budget += brand.daily_budget
            total_monthly_budget += brand.monthly_budget
            
            brand_detail: BrandDetail = {
                'id': int(brand.id),
                'name': brand.name,
                'daily_spend': str(brand.daily_spend),
                'daily_budget': str(brand.daily_budget),
                'monthly_spend': str(brand.monthly_spend),
                'monthly_budget': str(brand.monthly_budget),
                'daily_exceeded': brand.is_daily_budget_exceeded(),
                'monthly_exceeded': brand.is_monthly_budget_exceeded(),
                'active_campaigns': brand.campaigns.filter(is_active=True).count(),
                'paused_campaigns': brand.campaigns.filter(is_active=False).count()
            }
            brand_details.append(brand_detail)
        
        summary: BudgetSummary = {
            'total_brands': brands.count(),
            'brands_over_daily_budget': brands_over_daily_budget,
            'brands_over_monthly_budget': brands_over_monthly_budget,
            'total_daily_spend': str(total_daily_spend),
            'total_monthly_spend': str(total_monthly_spend),
            'total_daily_budget': str(total_daily_budget),
            'total_monthly_budget': str(total_monthly_budget),
            'brand_details': brand_details,
            'timestamp': timezone.now().isoformat()
        }
        
        return summary


class DaypartingService:
    """
    Service class for handling dayparting operations.
    """
    
    def __init__(self) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def update_all_campaigns(self) -> DaypartingUpdateResult:
        """
        Update dayparting status for all campaigns.
        Returns a summary of actions taken.
        """
        self.logger.info("Updating dayparting status for all campaigns")
        
        campaigns_checked = 0
        campaigns_activated = 0
        campaigns_deactivated = 0
        campaigns_unchanged = 0
        
        try:
            campaigns = Campaign.objects.select_related('brand').all()
            
            for campaign in campaigns:
                campaigns_checked += 1
                old_status = campaign.is_active
                
                # Update dayparting status
                campaign.update_dayparting_status()
                
                # Check if status changed
                if campaign.is_active != old_status:
                    if campaign.is_active:
                        campaigns_activated += 1
                    else:
                        campaigns_deactivated += 1
                else:
                    campaigns_unchanged += 1
            
            results: DaypartingUpdateResult = {
                'campaigns_checked': campaigns_checked,
                'campaigns_activated': campaigns_activated,
                'campaigns_deactivated': campaigns_deactivated,
                'campaigns_unchanged': campaigns_unchanged,
                'timestamp': timezone.now().isoformat()
            }
            
            self.logger.info(f"Dayparting update completed: {results}")
            return results
            
        except Exception as exc:
            self.logger.error(f"Error in dayparting update: {exc}")
            raise
    
    def update_campaign_dayparting(self, campaign_id: int) -> CampaignDaypartingResult:
        """
        Update dayparting status for a specific campaign.
        """
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        old_status = campaign.is_active
        old_dayparting_pause = campaign.is_paused_by_dayparting
        
        # Update dayparting status
        campaign.update_dayparting_status()
        
        results: CampaignDaypartingResult = {
            'campaign_id': campaign_id,
            'campaign_name': campaign.name,
            'brand_name': campaign.brand.name,
            'old_status': old_status,
            'new_status': campaign.is_active,
            'old_dayparting_pause': old_dayparting_pause,
            'new_dayparting_pause': campaign.is_paused_by_dayparting,
            'is_in_dayparting_window': campaign.is_in_dayparting_window(),
            'timestamp': timezone.now().isoformat()
        }
        
        if campaign.is_active != old_status:
            status_change = "activated" if campaign.is_active else "deactivated"
            self.logger.info(f"Campaign {campaign.name} {status_change} due to dayparting rules")
        
        return results
    
    def get_dayparting_summary(self) -> DaypartingSummary:
        """
        Get a summary of dayparting status for all campaigns.
        """
        campaigns = Campaign.objects.select_related('brand').all()
        
        campaigns_in_dayparting_window = 0
        campaigns_paused_by_dayparting = 0
        campaigns_with_schedules = 0
        campaigns_without_schedules = 0
        total_schedules = 0
        active_schedules = 0
        campaign_details: List[CampaignDetail] = []
        
        for campaign in campaigns:
            schedules = campaign.dayparting_schedules.all()
            schedule_count = schedules.count()
            
            if schedule_count > 0:
                campaigns_with_schedules += 1
                total_schedules += schedule_count
                active_schedules += schedules.filter(is_active=True).count()
            else:
                campaigns_without_schedules += 1
            
            if campaign.is_in_dayparting_window():
                campaigns_in_dayparting_window += 1
            
            if campaign.is_paused_by_dayparting:
                campaigns_paused_by_dayparting += 1
            
            campaign_detail: CampaignDetail = {
                'id': int(campaign.id),
                'name': campaign.name,
                'brand_name': campaign.brand.name,
                'is_active': campaign.is_active,
                'is_paused_by_dayparting': campaign.is_paused_by_dayparting,
                'is_in_dayparting_window': campaign.is_in_dayparting_window(),
                'schedule_count': schedule_count,
                'active_schedules': campaign.dayparting_schedules.filter(is_active=True).count()
            }
            campaign_details.append(campaign_detail)
        
        summary: DaypartingSummary = {
            'total_campaigns': campaigns.count(),
            'campaigns_in_dayparting_window': campaigns_in_dayparting_window,
            'campaigns_paused_by_dayparting': campaigns_paused_by_dayparting,
            'campaigns_with_schedules': campaigns_with_schedules,
            'campaigns_without_schedules': campaigns_without_schedules,
            'total_schedules': total_schedules,
            'active_schedules': active_schedules,
            'campaign_details': campaign_details,
            'timestamp': timezone.now().isoformat()
        }
        
        return summary
    
    def validate_dayparting_schedule(
        self, 
        campaign_id: int, 
        day_of_week: int, 
        start_time: str, 
        end_time: str
    ) -> ScheduleValidationResult:
        """
        Validate a dayparting schedule before creation.
        """
        from datetime import time
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return ScheduleValidationResult(
                valid=False,
                error=f'Campaign {campaign_id} not found',
                campaign_id=None,
                campaign_name=None,
                day_of_week=None,
                start_time=None,
                end_time=None
            )
        
        # Validate day of week
        if day_of_week not in range(7):
            return ScheduleValidationResult(
                valid=False,
                error='Day of week must be between 0 (Monday) and 6 (Sunday)',
                campaign_id=None,
                campaign_name=None,
                day_of_week=None,
                start_time=None,
                end_time=None
            )
        
        # Validate time format
        try:
            start_time_obj = time.fromisoformat(start_time)
            end_time_obj = time.fromisoformat(end_time)
        except ValueError:
            return ScheduleValidationResult(
                valid=False,
                error='Invalid time format. Use HH:MM:SS format',
                campaign_id=None,
                campaign_name=None,
                day_of_week=None,
                start_time=None,
                end_time=None
            )
        
        # Validate time range
        if start_time_obj >= end_time_obj:
            return ScheduleValidationResult(
                valid=False,
                error='Start time must be before end time',
                campaign_id=None,
                campaign_name=None,
                day_of_week=None,
                start_time=None,
                end_time=None
            )
        
        # Check for overlapping schedules
        overlapping = campaign.dayparting_schedules.filter(
            day_of_week=day_of_week,
            start_time__lt=end_time_obj,
            end_time__gt=start_time_obj
        ).exists()
        
        if overlapping:
            return ScheduleValidationResult(
                valid=False,
                error='Schedule overlaps with existing schedule for this day',
                campaign_id=None,
                campaign_name=None,
                day_of_week=None,
                start_time=None,
                end_time=None
            )
        
        return ScheduleValidationResult(
            valid=True,
            error=None,
            campaign_id=campaign_id,
            campaign_name=campaign.name,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time
        )
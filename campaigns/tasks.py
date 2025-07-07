"""
Celery tasks for budget management and campaign control.
"""
from celery import shared_task
from celery.app.task import Task
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from typing import Dict, Any, List, Optional, TypedDict, Literal
import logging
from datetime import datetime, timedelta

from .models import Brand, Campaign, Spend, DaypartingSchedule
from .services import BudgetService, DaypartingService, BudgetCheckResult, DaypartingUpdateResult

logger = logging.getLogger(__name__)

# Type aliases
ResetType = Literal['daily', 'monthly', 'both']
TaskStatus = Literal['completed', 'failed']

# TypedDict definitions for task return types
class TaskResult(TypedDict):
    timestamp: str
    status: TaskStatus


class BudgetDaypartingResult(TaskResult):
    budget_checks: BudgetCheckResult
    dayparting_updates: DaypartingUpdateResult


class ResetTaskResult(TaskResult):
    brands_reset: int
    campaigns_reactivated: int
    dayparting_updates: DaypartingUpdateResult


class CleanupResult(TaskResult):
    records_deleted: int
    cutoff_date: str


class SpendRecordResult(TaskResult):
    spend_id: int
    campaign_id: int
    campaign_name: str
    brand_name: str
    amount: str
    spent_at: str
    budget_check: Dict[str, Any]


class BrandResetResult(TaskResult):
    brand_id: int
    brand_name: str
    reset_type: ResetType
    campaigns_reactivated: int
    dayparting_updates: DaypartingUpdateResult


@shared_task(bind=True, max_retries=3)
def check_budgets_and_dayparting(self: Task) -> BudgetDaypartingResult:
    """
    Periodic task to check budget limits and enforce dayparting schedules.
    Runs every 15 minutes.
    """
    try:
        logger.info("Starting budget and dayparting check")
        
        # Initialize services
        budget_service = BudgetService()
        dayparting_service = DaypartingService()
        
        # Check budgets and pause campaigns if needed
        budget_results = budget_service.check_all_budgets()
        
        # Update dayparting status for all campaigns
        dayparting_results = dayparting_service.update_all_campaigns()
        
        results: BudgetDaypartingResult = {
            'timestamp': timezone.now().isoformat(),
            'budget_checks': budget_results,
            'dayparting_updates': dayparting_results,
            'status': 'completed'
        }
        
        logger.info(f"Budget and dayparting check completed: {results}")
        return results
        
    except Exception as exc:
        logger.error(f"Error in budget and dayparting check: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def daily_reset_task(self: Task) -> ResetTaskResult:
    """
    Daily reset task that runs at midnight.
    Resets daily spend totals and reactivates eligible campaigns.
    """
    try:
        logger.info("Starting daily reset")
        
        with transaction.atomic():
            # Reset daily spend for all brands
            brands = Brand.objects.all()
            reset_count = 0
            reactivated_count = 0
            
            for brand in brands:
                # Reset daily spend
                brand.reset_daily_spend()
                reset_count += 1
                
                # Reactivate campaigns if monthly budget allows
                if not brand.is_monthly_budget_exceeded():
                    reactivated = brand.reactivate_campaigns()
                    reactivated_count += reactivated
                    logger.info(f"Reactivated {reactivated} campaigns for brand {brand.name}")
                else:
                    logger.info(f"Brand {brand.name} monthly budget exceeded, campaigns remain paused")
            
            # Update dayparting status for all campaigns
            dayparting_service = DaypartingService()
            dayparting_results = dayparting_service.update_all_campaigns()
            
            results: ResetTaskResult = {
                'timestamp': timezone.now().isoformat(),
                'brands_reset': reset_count,
                'campaigns_reactivated': reactivated_count,
                'dayparting_updates': dayparting_results,
                'status': 'completed'
            }
            
            logger.info(f"Daily reset completed: {results}")
            return results
            
    except Exception as exc:
        logger.error(f"Error in daily reset: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def monthly_reset_task(self: Task) -> ResetTaskResult:
    """
    Monthly reset task that runs on the 1st of each month at midnight.
    Resets both daily and monthly spend totals and reactivates all campaigns.
    """
    try:
        logger.info("Starting monthly reset")
        
        with transaction.atomic():
            # Reset both daily and monthly spend for all brands
            brands = Brand.objects.all()
            reset_count = 0
            reactivated_count = 0
            
            for brand in brands:
                # Reset both daily and monthly spend
                brand.reset_daily_spend()
                brand.reset_monthly_spend()
                reset_count += 1
                
                # Reactivate all campaigns paused by budget
                reactivated = brand.reactivate_campaigns()
                reactivated_count += reactivated
                logger.info(f"Reactivated {reactivated} campaigns for brand {brand.name}")
            
            # Update dayparting status for all campaigns
            dayparting_service = DaypartingService()
            dayparting_results = dayparting_service.update_all_campaigns()
            
            results: ResetTaskResult = {
                'timestamp': timezone.now().isoformat(),
                'brands_reset': reset_count,
                'campaigns_reactivated': reactivated_count,
                'dayparting_updates': dayparting_results,
                'status': 'completed'
            }
            
            logger.info(f"Monthly reset completed: {results}")
            return results
            
    except Exception as exc:
        logger.error(f"Error in monthly reset: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def cleanup_old_spends(self: Task, days_to_keep: int = 90) -> CleanupResult:
    """
    Cleanup old spend records to maintain database performance.
    Runs weekly on Monday at 2 AM.
    """
    try:
        logger.info(f"Starting cleanup of spend records older than {days_to_keep} days")
        
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        # Count records to be deleted
        old_spends = Spend.objects.filter(spent_at__lt=cutoff_date)
        count = old_spends.count()
        
        # Delete old records in batches to avoid memory issues
        batch_size = 1000
        deleted_count = 0
        
        while old_spends.exists():
            batch_ids = list(old_spends.values_list('id', flat=True)[:batch_size])
            deleted_batch = Spend.objects.filter(id__in=batch_ids).delete()
            deleted_count += deleted_batch[0]
            
            if deleted_batch[0] == 0:
                break
        
        results: CleanupResult = {
            'timestamp': timezone.now().isoformat(),
            'records_deleted': deleted_count,
            'cutoff_date': cutoff_date.isoformat(),
            'status': 'completed'
        }
        
        logger.info(f"Cleanup completed: {results}")
        return results
        
    except Exception as exc:
        logger.error(f"Error in cleanup task: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True)
def record_spend(self: Task, campaign_id: int, amount: float, spent_at: Optional[str] = None) -> SpendRecordResult:
    """
    Task to record a new spend and update budget totals.
    This can be called from external systems or APIs.
    """
    try:
        logger.info(f"Recording spend of ${amount} for campaign {campaign_id}")
        
        # Get the campaign
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        # Convert amount to Decimal
        amount_decimal = Decimal(str(amount))
        
        # Parse spent_at if provided
        spent_at_datetime = None
        if spent_at:
            spent_at_datetime = datetime.fromisoformat(spent_at.replace('Z', '+00:00'))
        
        # Create spend record
        spend = Spend.objects.create(
            campaign=campaign,
            amount=amount_decimal,
            spent_at=spent_at_datetime if spent_at_datetime else timezone.now()
        )
        
        # Check if this spend pushed the brand over budget
        budget_service = BudgetService()
        budget_results = budget_service.check_brand_budget(int(campaign.brand.id))
        
        results: SpendRecordResult = {
            'timestamp': timezone.now().isoformat(),
            'spend_id': int(spend.id),
            'campaign_id': campaign_id,
            'campaign_name': campaign.name,
            'brand_name': campaign.brand.name,
            'amount': str(amount_decimal),
            'spent_at': spend.spent_at.isoformat(),
            'budget_check': dict(budget_results),
            'status': 'completed'
        }
        
        logger.info(f"Spend recorded successfully: {results}")
        return results
        
    except Exception as exc:
        logger.error(f"Error recording spend: {exc}")
        raise


@shared_task(bind=True)
def update_campaign_dayparting(self: Task, campaign_id: int) -> Dict[str, Any]:
    """
    Task to update dayparting status for a specific campaign.
    """
    try:
        logger.info(f"Updating dayparting status for campaign {campaign_id}")
        
        # Initialize service
        dayparting_service = DaypartingService()
        
        # Update campaign dayparting
        results = dayparting_service.update_campaign_dayparting(campaign_id)
        
        logger.info(f"Campaign dayparting updated: {results}")
        # Convert to dict for compatibility
        return dict(results)
        
    except Exception as exc:
        logger.error(f"Error updating campaign dayparting: {exc}")
        raise


@shared_task(bind=True)
def force_brand_reset(self: Task, brand_id: int, reset_type: ResetType = 'daily') -> BrandResetResult:
    """
    Task to force reset of brand spend totals.
    
    Args:
        brand_id: ID of the brand to reset
        reset_type: 'daily', 'monthly', or 'both'
    """
    try:
        logger.info(f"Force resetting {reset_type} spend for brand {brand_id}")
        
        # Get the brand
        try:
            brand = Brand.objects.get(id=brand_id)
        except Brand.DoesNotExist:
            raise ValueError(f"Brand {brand_id} not found")
        
        # Reset based on type
        if reset_type == 'daily':
            brand.reset_daily_spend()
        elif reset_type == 'monthly':
            brand.reset_monthly_spend()
        elif reset_type == 'both':
            brand.reset_daily_spend()
            brand.reset_monthly_spend()
        else:
            raise ValueError(f"Invalid reset_type: {reset_type}")
        
        # Reactivate campaigns
        reactivated_count = brand.reactivate_campaigns()
        
        # Update dayparting status
        dayparting_service = DaypartingService()
        dayparting_results = dayparting_service.update_all_campaigns()
        
        results: BrandResetResult = {
            'timestamp': timezone.now().isoformat(),
            'brand_id': brand_id,
            'brand_name': brand.name,
            'reset_type': reset_type,
            'campaigns_reactivated': reactivated_count,
            'dayparting_updates': dayparting_results,
            'status': 'completed'
        }
        
        logger.info(f"Brand reset completed: {results}")
        return results
        
    except Exception as exc:
        logger.error(f"Error in brand reset: {exc}")
        raise 
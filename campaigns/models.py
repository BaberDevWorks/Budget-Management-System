"""
Django models for the budget management system.
"""
from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Final
from datetime import datetime, time
import logging

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)

# Constants
DAYS_OF_WEEK: Final[List[tuple[int, str]]] = [
    (0, 'Monday'),
    (1, 'Tuesday'),
    (2, 'Wednesday'),
    (3, 'Thursday'),
    (4, 'Friday'),
    (5, 'Saturday'),
    (6, 'Sunday'),
]


class Brand(models.Model):
    """
    Brand model representing advertising brands with budget limits.
    """
    name = models.CharField(max_length=200, unique=True)
    daily_budget = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    monthly_budget = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    daily_spend = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    monthly_spend = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        # Type hints for static analysis
        id: int

    class Meta:
        db_table = 'brands'
        ordering = ['name']

    def __str__(self) -> str:
        return str(self.name)

    def is_daily_budget_exceeded(self) -> bool:
        """Check if daily budget is exceeded."""
        return bool(self.daily_spend >= self.daily_budget)

    def is_monthly_budget_exceeded(self) -> bool:
        """Check if monthly budget is exceeded."""
        return bool(self.monthly_spend >= self.monthly_budget)

    def remaining_daily_budget(self) -> Decimal:
        """Calculate remaining daily budget."""
        return Decimal(str(max(Decimal('0.00'), self.daily_budget - self.daily_spend)))

    def remaining_monthly_budget(self) -> Decimal:
        """Calculate remaining monthly budget."""
        return Decimal(str(max(Decimal('0.00'), self.monthly_budget - self.monthly_spend)))

    def add_spend(self, amount: Decimal) -> None:
        """
        Add spend amount to both daily and monthly totals.
        This method uses atomic transactions to prevent race conditions.
        """
        if amount <= 0:
            raise ValueError("Spend amount must be positive")
        
        with transaction.atomic():
            # Select for update to prevent race conditions
            brand = Brand.objects.select_for_update().get(pk=self.pk)
            brand.daily_spend += amount
            brand.monthly_spend += amount
            brand.save(update_fields=['daily_spend', 'monthly_spend', 'updated_at'])
            
            # Update current instance
            self.daily_spend = brand.daily_spend
            self.monthly_spend = brand.monthly_spend
            self.updated_at = brand.updated_at

    def reset_daily_spend(self) -> None:
        """Reset daily spend to zero."""
        self.daily_spend = Decimal('0.00')
        self.save(update_fields=['daily_spend', 'updated_at'])

    def reset_monthly_spend(self) -> None:
        """Reset monthly spend to zero."""
        self.monthly_spend = Decimal('0.00')
        self.save(update_fields=['monthly_spend', 'updated_at'])

    def pause_all_campaigns(self, reason: str = 'budget') -> int:
        """
        Pause all campaigns belonging to this brand.
        Returns the number of campaigns paused.
        """
        campaigns = self.campaigns.filter(is_active=True)
        count = campaigns.count()
        
        if reason == 'budget':
            campaigns.update(
                is_paused_by_budget=True,
                is_active=False,
                updated_at=timezone.now()
            )
        
        logger.info(f"Paused {count} campaigns for brand {self.name} due to {reason}")
        return int(count)

    def reactivate_campaigns(self) -> int:
        """
        Reactivate campaigns that were paused due to budget constraints.
        Applies dayparting rules to determine final active state.
        Returns the number of campaigns reactivated.
        """
        campaigns = self.campaigns.filter(is_paused_by_budget=True)
        count = 0
        
        for campaign in campaigns:
            campaign.is_paused_by_budget = False
            # Apply dayparting rules to determine if campaign should be active
            if campaign.is_in_dayparting_window():
                campaign.is_active = True
                count += 1
            else:
                campaign.is_paused_by_dayparting = True
                campaign.is_active = False
            campaign.save()
        
        logger.info(f"Reactivated {count} campaigns for brand {self.name}")
        return count


class Campaign(models.Model):
    """
    Campaign model representing advertising campaigns.
    """
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='campaigns')
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    is_paused_by_budget = models.BooleanField(default=False)
    is_paused_by_dayparting = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        # Type hints for static analysis
        id: int

    class Meta:
        db_table = 'campaigns'
        ordering = ['brand__name', 'name']
        unique_together = ['brand', 'name']

    def __str__(self) -> str:
        return f"{self.brand.name} - {self.name}"

    def is_in_dayparting_window(self) -> bool:
        """
        Check if the campaign is currently within its dayparting window.
        """
        now = timezone.now()
        current_time = now.time()
        current_day = now.weekday()  # 0=Monday, 6=Sunday
        
        # If no dayparting schedules exist, campaign can run anytime
        if not self.dayparting_schedules.exists():
            return True
        
        # Check if current time falls within any active schedule
        for schedule in self.dayparting_schedules.filter(is_active=True):
            if schedule.day_of_week == current_day:
                if schedule.start_time <= current_time <= schedule.end_time:
                    return True
        
        return False

    def update_dayparting_status(self) -> None:
        """
        Update the campaign's dayparting status and active state.
        """
        is_in_window = self.is_in_dayparting_window()
        
        if is_in_window and not self.is_paused_by_budget:
            self.is_paused_by_dayparting = False
            self.is_active = True
        else:
            self.is_paused_by_dayparting = not is_in_window
            self.is_active = False
        
        self.save(update_fields=['is_paused_by_dayparting', 'is_active', 'updated_at'])

    def total_spend_today(self) -> Decimal:
        """Calculate total spend for today."""
        today = timezone.now().date()
        result = self.spends.filter(
            spent_at__date=today
        ).aggregate(
            total=models.Sum('amount')
        )['total']
        return result or Decimal('0.00')

    def total_spend_this_month(self) -> Decimal:
        """Calculate total spend for current month."""
        now = timezone.now()
        result = self.spends.filter(
            spent_at__year=now.year,
            spent_at__month=now.month
        ).aggregate(
            total=models.Sum('amount')
        )['total']
        return result or Decimal('0.00')


class Spend(models.Model):
    """
    Spend model representing individual ad spend records.
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='spends')
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    spent_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        # Type hints for static analysis
        id: int

    class Meta:
        db_table = 'spends'
        ordering = ['-spent_at']
        indexes = [
            models.Index(fields=['campaign', '-spent_at']),
            models.Index(fields=['spent_at']),
        ]

    def __str__(self) -> str:
        return f"{self.campaign.name} - ${self.amount} on {self.spent_at.date()}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        Override save to automatically update brand spend totals.
        """
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            # Update brand spend totals
            self.campaign.brand.add_spend(self.amount)
            logger.info(f"Recorded spend of ${self.amount} for campaign {self.campaign.name}")


class DaypartingSchedule(models.Model):
    """
    DaypartingSchedule model representing time-based campaign scheduling.
    """
    campaign = models.ForeignKey(
        Campaign, 
        on_delete=models.CASCADE, 
        related_name='dayparting_schedules'
    )
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        # Type hints for static analysis
        id: int

    class Meta:
        db_table = 'dayparting_schedules'
        ordering = ['day_of_week', 'start_time']
        unique_together = ['campaign', 'day_of_week', 'start_time']

    def __str__(self) -> str:
        day_name = self.get_day_of_week_display()
        return f"{self.campaign.name} - {day_name} {self.start_time}-{self.end_time}"

    def clean(self) -> None:
        """
        Validate that start_time is before end_time.
        """
        from django.core.exceptions import ValidationError
        
        if self.start_time >= self.end_time:
            raise ValidationError("Start time must be before end time")

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        Override save to perform validation.
        """
        self.clean()
        super().save(*args, **kwargs)

    def is_active_now(self) -> bool:
        """
        Check if this schedule is currently active.
        """
        if not self.is_active:
            return False
        
        now = timezone.now()
        current_time = now.time()
        current_day = now.weekday()
        
        return bool(
            self.day_of_week == current_day and
            self.start_time <= current_time <= self.end_time
        ) 
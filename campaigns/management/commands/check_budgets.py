"""
Management command to check budgets manually.
"""
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone
from typing import Any, Dict, List, Optional, Union
import logging

from campaigns.services import BudgetService, DaypartingService, BudgetCheckResult, BrandBudgetResult, DaypartingUpdateResult
from campaigns.models import Brand, Campaign


class Command(BaseCommand):
    """
    Management command to check budgets and update campaign statuses.
    
    This command can be used to manually trigger budget checks and
    campaign status updates, useful for testing and debugging.
    """
    
    help = 'Check budget limits and update campaign statuses'
    
    def add_arguments(self, parser: CommandParser) -> None:
        """Add command arguments."""
        parser.add_argument(
            '--brand-id',
            type=int,
            help='Check budget for specific brand only'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )
    
    def handle(self, *args: Any, **options: Any) -> None:
        """Handle the command execution."""
        try:
            # Set up logging
            if options['verbose']:
                logging.basicConfig(level=logging.INFO)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting budget check at {timezone.now()}"
                )
            )
            
            # Initialize services
            budget_service = BudgetService()
            dayparting_service = DaypartingService()
            
            # Check specific brand or all brands
            if options['brand_id']:
                self._check_single_brand(budget_service, options['brand_id'], options['dry_run'])
            else:
                self._check_all_brands(budget_service, options['dry_run'])
            
            # Update dayparting status
            self._update_dayparting(dayparting_service, options['dry_run'])
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Budget check completed at {timezone.now()}"
                )
            )
            
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"Error during budget check: {e}")
            )
            raise CommandError(f"Budget check failed: {e}")
    
    def _check_single_brand(self, budget_service: BudgetService, brand_id: int, dry_run: bool) -> None:
        """Check budget for a single brand."""
        try:
            brand = Brand.objects.get(id=brand_id)
            self.stdout.write(f"Checking budget for brand: {brand.name}")
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN: No changes will be made")
                )
                
                # Show current status
                self.stdout.write(f"Daily spend: ${brand.daily_spend} / ${brand.daily_budget}")
                self.stdout.write(f"Monthly spend: ${brand.monthly_spend} / ${brand.monthly_budget}")
                self.stdout.write(f"Daily exceeded: {brand.is_daily_budget_exceeded()}")
                self.stdout.write(f"Monthly exceeded: {brand.is_monthly_budget_exceeded()}")
            else:
                results = budget_service.check_brand_budget(brand_id)
                self._display_results(dict(results))
                
        except Brand.DoesNotExist:
            raise CommandError(f"Brand {brand_id} not found")
    
    def _check_all_brands(self, budget_service: BudgetService, dry_run: bool) -> None:
        """Check budgets for all brands."""
        self.stdout.write("Checking budgets for all brands")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN: No changes will be made")
            )
            
            brands = Brand.objects.filter(is_active=True)
            for brand in brands:
                self.stdout.write(f"\nBrand: {brand.name}")
                self.stdout.write(f"  Daily: ${brand.daily_spend} / ${brand.daily_budget}")
                self.stdout.write(f"  Monthly: ${brand.monthly_spend} / ${brand.monthly_budget}")
                self.stdout.write(f"  Daily exceeded: {brand.is_daily_budget_exceeded()}")
                self.stdout.write(f"  Monthly exceeded: {brand.is_monthly_budget_exceeded()}")
        else:
            results = budget_service.check_all_budgets()
            self._display_results(dict(results))
    
    def _update_dayparting(self, dayparting_service: DaypartingService, dry_run: bool) -> None:
        """Update dayparting status for all campaigns."""
        self.stdout.write("\nUpdating dayparting status for all campaigns")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN: No dayparting changes will be made")
            )
            
            campaigns = Campaign.objects.select_related('brand').all()
            for campaign in campaigns:
                in_window = campaign.is_in_dayparting_window()
                self.stdout.write(f"  {campaign.name}: In window = {in_window}")
        else:
            results = dayparting_service.update_all_campaigns()
            self._display_results(dict(results))
    
    def _display_results(self, results: Dict[str, Any]) -> None:
        """Display results in a formatted way."""
        self.stdout.write("\nResults:")
        # Convert TypedDict to regular dict for iteration
        for key, value in results.items():
            if key == 'timestamp':
                continue
            self.stdout.write(f"  {key}: {value}")
        
        # Show any warnings or errors
        if 'brands_over_daily_budget' in results and results['brands_over_daily_budget'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  {results['brands_over_daily_budget']} brands exceeded daily budget"
                )
            )
        
        if 'brands_over_monthly_budget' in results and results['brands_over_monthly_budget'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  {results['brands_over_monthly_budget']} brands exceeded monthly budget"
                )
            )
        
        if 'campaigns_paused' in results and results['campaigns_paused'] and results['campaigns_paused'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  {results['campaigns_paused']} campaigns paused due to budget limits"
                )
            )
        
        if 'campaigns_reactivated' in results and results['campaigns_reactivated'] and results['campaigns_reactivated'] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ {results['campaigns_reactivated']} campaigns reactivated"
                )
            ) 
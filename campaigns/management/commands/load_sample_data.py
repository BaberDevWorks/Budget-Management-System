"""
Management command to load sample data for testing.
"""
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from datetime import time, timedelta
from typing import Any, Dict, List
import random

from campaigns.models import Brand, Campaign, Spend, DaypartingSchedule


class Command(BaseCommand):
    """
    Management command to load sample data for testing the budget management system.
    
    This command creates sample brands, campaigns, dayparting schedules, and spend records
    to test the system functionality.
    """
    
    help = 'Load sample data for testing the budget management system'
    
    def add_arguments(self, parser: CommandParser) -> None:
        """Add command arguments."""
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before loading sample data'
        )
        parser.add_argument(
            '--brands',
            type=int,
            default=5,
            help='Number of brands to create (default: 5)'
        )
        parser.add_argument(
            '--campaigns-per-brand',
            type=int,
            default=3,
            help='Number of campaigns per brand (default: 3)'
        )
    
    def handle(self, *args: Any, **options: Any) -> None:
        """Handle the command execution."""
        if options['clear']:
            self._clear_data()
        
        self._create_brands(options['brands'])
        self._create_campaigns(options['campaigns_per_brand'])
        self._create_dayparting_schedules()
        self._create_sample_spends()
        
        self.stdout.write(
            self.style.SUCCESS(
                "Sample data loaded successfully!"
            )
        )
    
    def _clear_data(self) -> None:
        """Clear existing data."""
        self.stdout.write("Clearing existing data...")
        
        # Delete in reverse order of dependencies
        Spend.objects.all().delete()
        DaypartingSchedule.objects.all().delete()
        Campaign.objects.all().delete()
        Brand.objects.all().delete()
        
        self.stdout.write("Existing data cleared.")
    
    def _create_brands(self, count: int) -> None:
        """Create sample brands."""
        self.stdout.write(f"Creating {count} brands...")
        
        brand_names = [
            "Nike", "Adidas", "Apple", "Samsung", "Coca-Cola",
            "Pepsi", "McDonald's", "Starbucks", "Amazon", "Netflix"
        ]
        
        brands = []
        for i in range(count):
            name = brand_names[i % len(brand_names)]
            if i >= len(brand_names):
                name = f"{name} {i - len(brand_names) + 2}"
            
            brand, created = Brand.objects.get_or_create(
                name=name,
                defaults={
                    'daily_budget': Decimal(str(random.randint(500, 5000))),
                    'monthly_budget': Decimal(str(random.randint(10000, 50000))),
                    'daily_spend': Decimal('0.00'),
                    'monthly_spend': Decimal('0.00'),
                    'is_active': True
                }
            )
            brands.append(brand)
            
            if created:
                self.stdout.write(f"Created brand: {name}")
            else:
                self.stdout.write(f"Brand already exists: {name}")
        
        self.stdout.write(f"Processed {len(brands)} brands.")
    
    def _create_campaigns(self, campaigns_per_brand: int) -> None:
        """Create sample campaigns."""
        brands = Brand.objects.all()
        total_campaigns = 0
        
        campaign_types = [
            "Search", "Display", "Video", "Social", "Shopping",
            "Email", "Mobile", "Retargeting", "Brand Awareness", "Conversion"
        ]
        
        self.stdout.write(f"Creating {campaigns_per_brand} campaigns per brand...")
        
        for brand in brands:
            for i in range(campaigns_per_brand):
                campaign_type = random.choice(campaign_types)
                campaign_name = f"{brand.name} {campaign_type} Campaign {i + 1}"
                
                campaign, created = Campaign.objects.get_or_create(
                    name=campaign_name,
                    brand=brand,
                    defaults={
                        'is_active': True,
                        'is_paused_by_budget': False,
                        'is_paused_by_dayparting': False
                    }
                )
                
                if created:
                    total_campaigns += 1
                    self.stdout.write(f"Created campaign: {campaign_name}")
                else:
                    self.stdout.write(f"Campaign already exists: {campaign_name}")
        
        self.stdout.write(f"Processed {total_campaigns} new campaigns.")
    
    def _create_dayparting_schedules(self) -> None:
        """Create sample dayparting schedules."""
        campaigns = Campaign.objects.all()
        total_schedules = 0
        
        self.stdout.write("Creating dayparting schedules...")
        
        # Define some common dayparting patterns
        patterns = [
            # Business hours (9-5, Mon-Fri)
            [(i, time(9, 0), time(17, 0)) for i in range(5)],
            # Extended hours (8-6, Mon-Fri)
            [(i, time(8, 0), time(18, 0)) for i in range(5)],
            # Weekend only
            [(5, time(10, 0), time(22, 0)), (6, time(10, 0), time(22, 0))],
            # All week, evening hours
            [(i, time(18, 0), time(23, 0)) for i in range(7)],
            # All week, daytime hours
            [(i, time(9, 0), time(17, 0)) for i in range(7)],
        ]
        
        for campaign in campaigns:
            # 70% chance of having dayparting schedules
            if random.random() < 0.7:
                pattern = random.choice(patterns)
                for day, start_time, end_time in pattern:
                    schedule, created = DaypartingSchedule.objects.get_or_create(
                        campaign=campaign,
                        day_of_week=day,
                        start_time=start_time,
                        end_time=end_time,
                        defaults={
                            'is_active': True
                        }
                    )
                    if created:
                        total_schedules += 1
        
        self.stdout.write(f"Created {total_schedules} dayparting schedules.")
    
    def _create_sample_spends(self) -> None:
        """Create sample spend records."""
        campaigns = Campaign.objects.all()
        total_spends = 0
        
        self.stdout.write("Creating sample spend records...")
        
        # Create spends for the last 7 days
        for campaign in campaigns:
            # Create random spends for each campaign
            spend_count = random.randint(5, 20)
            
            for _ in range(spend_count):
                # Random amount between $1 and $100
                amount = Decimal(str(round(random.uniform(1.0, 100.0), 2)))
                
                # Random timestamp in the last 7 days
                days_ago = random.randint(0, 7)
                hours_ago = random.randint(0, 23)
                minutes_ago = random.randint(0, 59)
                
                spent_at = timezone.now() - timedelta(
                    days=days_ago,
                    hours=hours_ago,
                    minutes=minutes_ago
                )
                
                # Create spend record
                spend, created = Spend.objects.get_or_create(
                    campaign=campaign,
                    amount=amount,
                    spent_at=spent_at,
                    defaults={
                        'created_at': timezone.now()
                    }
                )
                
                if created:
                    total_spends += 1
        
        self.stdout.write(f"Created {total_spends} spend records.")
        
        # Update brand spend totals
        self._update_brand_spends()
    
    def _update_brand_spends(self) -> None:
        """Update brand spend totals based on created spend records."""
        self.stdout.write("Updating brand spend totals...")
        
        brands = Brand.objects.all()
        for brand in brands:
            # Calculate total spend for this brand
            # Type ignore for Django's reverse foreign key relationship
            brand_spends = Spend.objects.filter(campaign__brand=brand)
            
            # Calculate daily spend (today only)
            today = timezone.now().date()
            daily_total = brand_spends.filter(
                spent_at__date=today
            ).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')
            
            # Calculate monthly spend (this month)
            now = timezone.now()
            monthly_total = brand_spends.filter(
                spent_at__year=now.year,
                spent_at__month=now.month
            ).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')
            
            # Update brand totals
            brand.daily_spend = daily_total
            brand.monthly_spend = monthly_total
            brand.save(update_fields=['daily_spend', 'monthly_spend'])
            
            self.stdout.write(f"Updated {brand.name}: Daily=${daily_total}, Monthly=${monthly_total}")
        
        self.stdout.write("Brand spend totals updated.")

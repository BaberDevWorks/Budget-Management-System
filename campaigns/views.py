"""
Views for the campaigns app.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q
from django.utils import timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional, Union, Literal
import json
import logging

from .models import Brand, Campaign, Spend, DaypartingSchedule
from .services import BudgetService, DaypartingService
from .tasks import record_spend, update_campaign_dayparting, force_brand_reset

logger = logging.getLogger(__name__)

# Type aliases for status filtering
StatusFilter = Literal['all', 'active', 'inactive', 'budget_paused', 'dayparting_paused']


def dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard view showing budget and campaign status.
    """
    budget_service = BudgetService()
    dayparting_service = DaypartingService()
    
    try:
        # Get budget summary
        budget_summary = budget_service.get_budget_summary()
        
        # Get dayparting summary
        dayparting_summary = dayparting_service.get_dayparting_summary()
        
        # Get recent spends
        recent_spends = Spend.objects.select_related('campaign', 'campaign__brand').order_by('-spent_at')[:10]
        
        context = {
            'budget_summary': budget_summary,
            'dayparting_summary': dayparting_summary,
            'recent_spends': recent_spends,
            'timestamp': timezone.now(),
        }
        
        return render(request, 'campaigns/dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error in dashboard view: {e}")
        messages.error(request, "Error loading dashboard data")
        return render(request, 'campaigns/dashboard.html', {})


def brand_list(request: HttpRequest) -> HttpResponse:
    """
    List all brands with their budget status.
    """
    brands = Brand.objects.annotate(
        campaign_count=Count('campaigns'),
        active_campaign_count=Count('campaigns', filter=Q(campaigns__is_active=True))
    ).order_by('name')
    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        brands = brands.filter(name__icontains=search_query)
    
    # Handle pagination
    paginator = Paginator(brands, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'brands': page_obj,
        'search_query': search_query,
        'total_brands': paginator.count,
    }
    
    return render(request, 'campaigns/brand_list.html', context)


def brand_detail(request: HttpRequest, brand_id: int) -> HttpResponse:
    """
    Show detailed information about a specific brand.
    """
    brand = get_object_or_404(Brand, id=brand_id)
    
    # Get campaigns with status filtering
    campaigns = brand.campaigns.select_related('brand').all()
    
    # Handle status filter
    status: StatusFilter = request.GET.get('status', 'all')  # type: ignore
    if status == 'active':
        campaigns = campaigns.filter(is_active=True)
    elif status == 'inactive':
        campaigns = campaigns.filter(is_active=False)
    elif status == 'budget_paused':
        campaigns = campaigns.filter(is_paused_by_budget=True)
    elif status == 'dayparting_paused':
        campaigns = campaigns.filter(is_paused_by_dayparting=True)
    
    # Get recent spends for this brand
    recent_spends = Spend.objects.filter(
        campaign__brand=brand
    ).select_related('campaign').order_by('-spent_at')[:20]
    
    context = {
        'brand': brand,
        'campaigns': campaigns,
        'recent_spends': recent_spends,
        'status_filter': status,
        'budget_exceeded': brand.is_daily_budget_exceeded() or brand.is_monthly_budget_exceeded(),
    }
    
    return render(request, 'campaigns/brand_detail.html', context)


def campaign_list(request: HttpRequest) -> HttpResponse:
    """
    List all campaigns with their status.
    """
    campaigns = Campaign.objects.select_related('brand').annotate(
        spend_count=Count('spends'),
        total_spend=Sum('spends__amount')
    ).order_by('brand__name', 'name')
    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        campaigns = campaigns.filter(
            Q(name__icontains=search_query) | 
            Q(brand__name__icontains=search_query)
        )
    
    # Handle status filter
    status: StatusFilter = request.GET.get('status', 'all')  # type: ignore
    if status == 'active':
        campaigns = campaigns.filter(is_active=True)
    elif status == 'inactive':
        campaigns = campaigns.filter(is_active=False)
    elif status == 'budget_paused':
        campaigns = campaigns.filter(is_paused_by_budget=True)
    elif status == 'dayparting_paused':
        campaigns = campaigns.filter(is_paused_by_dayparting=True)
    
    # Handle pagination
    paginator = Paginator(campaigns, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'campaigns': page_obj,
        'search_query': search_query,
        'status_filter': status,
        'total_campaigns': paginator.count,
    }
    
    return render(request, 'campaigns/campaign_list.html', context)


def campaign_detail(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """
    Show detailed information about a specific campaign.
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    
    # Get dayparting schedules
    schedules = campaign.dayparting_schedules.all().order_by('day_of_week', 'start_time')
    
    # Get recent spends
    recent_spends = campaign.spends.order_by('-spent_at')[:50]
    
    context = {
        'campaign': campaign,
        'schedules': schedules,
        'recent_spends': recent_spends,
        'is_in_dayparting_window': campaign.is_in_dayparting_window(),
        'today_spend': campaign.total_spend_today(),
        'month_spend': campaign.total_spend_this_month(),
    }
    
    return render(request, 'campaigns/campaign_detail.html', context)


@require_http_methods(["POST"])
def reset_brand_budget(request: HttpRequest, brand_id: int) -> HttpResponse:
    """
    Reset brand budget totals (daily or monthly).
    """
    from campaigns.tasks import ResetType
    
    reset_type_str = request.POST.get('reset_type', 'daily')
    
    if reset_type_str not in ['daily', 'monthly', 'both']:
        messages.error(request, "Invalid reset type")
        return redirect('brand_detail', brand_id=brand_id)
    
    try:
        # Queue the reset task - cast to ResetType for type safety
        reset_type: ResetType = reset_type_str  # type: ignore
        force_brand_reset.delay(brand_id, reset_type)
        
        messages.success(request, f"Brand {reset_type} budget reset queued successfully")
        
    except Exception as e:
        logger.error(f"Error queuing brand reset: {e}")
        messages.error(request, "Error queuing budget reset")
    
    return redirect('brand_detail', brand_id=brand_id)


@require_http_methods(["POST"])
def record_manual_spend(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """
    Record a manual spend for a campaign.
    """
    try:
        amount = Decimal(request.POST.get('amount', '0'))
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        # Queue the spend recording task
        record_spend.delay(campaign_id, float(amount))
        
        messages.success(request, f"Spend of ${amount} recorded successfully")
        
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid spend amount: {e}")
        messages.error(request, "Invalid spend amount")
    except Exception as e:
        logger.error(f"Error recording spend: {e}")
        messages.error(request, "Error recording spend")
    
    return redirect('campaign_detail', campaign_id=campaign_id)


def budget_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for budget information.
    """
    try:
        budget_service = BudgetService()
        
        if request.method == 'GET':
            # Get budget summary
            summary = budget_service.get_budget_summary()
            return JsonResponse(dict(summary))
            
        elif request.method == 'POST':
            # Trigger budget check
            results = budget_service.check_all_budgets()
            return JsonResponse(dict(results))
            
    except Exception as e:
        logger.error(f"Error in budget API: {e}")
        return JsonResponse({'error': 'An error occurred while processing the budget request'}, status=400)
        
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def dayparting_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for dayparting information.
    """
    try:
        dayparting_service = DaypartingService()
        
        if request.method == 'GET':
            # Get dayparting summary
            summary = dayparting_service.get_dayparting_summary()
            return JsonResponse(dict(summary))
            
        elif request.method == 'POST':
            # Trigger dayparting update
            results = dayparting_service.update_all_campaigns()
            return JsonResponse(dict(results))
            
    except Exception as e:
        logger.error(f"Error in dayparting API: {e}")
        return JsonResponse({'error': 'An error occurred while processing the dayparting request'}, status=400)
        
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def campaign_dayparting_api(request: HttpRequest, campaign_id: int) -> JsonResponse:
    """
    API endpoint for specific campaign dayparting.
    """
    try:
        dayparting_service = DaypartingService()
        
        if request.method == 'GET':
            # Get campaign dayparting info
            campaign = get_object_or_404(Campaign, id=campaign_id)
            data = {
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'is_active': campaign.is_active,
                'is_paused_by_dayparting': campaign.is_paused_by_dayparting,
                'is_in_dayparting_window': campaign.is_in_dayparting_window(),
                'schedules': [
                    {
                        'day_of_week': schedule.day_of_week,
                        'start_time': schedule.start_time.strftime('%H:%M:%S'),
                        'end_time': schedule.end_time.strftime('%H:%M:%S'),
                        'is_active': schedule.is_active,
                    }
                    for schedule in campaign.dayparting_schedules.all()
                ]
            }
            return JsonResponse(data)
            
        elif request.method == 'POST':
            # Update campaign dayparting
            results = dayparting_service.update_campaign_dayparting(campaign_id)
            return JsonResponse(dict(results))
            
    except Exception as e:
        logger.error(f"Error in campaign dayparting API: {e}")
        return JsonResponse({'error': 'An error occurred while processing the campaign dayparting request'}, status=400)
        
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@require_http_methods(["POST"])
def record_spend_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to record a new spend.
    
    Expected JSON payload:
    {
        "campaign_id": 123,
        "amount": 50.00,
        "spent_at": "2023-12-01T10:00:00Z"  # Optional
    }
    """
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        if 'campaign_id' not in data or 'amount' not in data:
            return JsonResponse({
                'error': 'Missing required fields: campaign_id and amount'
            }, status=400)
        
        campaign_id = int(data['campaign_id'])
        amount = float(data['amount'])
        spent_at = data.get('spent_at')
        
        # Validate amount
        if amount <= 0:
            return JsonResponse({
                'error': 'Amount must be positive'
            }, status=400)
        
        # Validate campaign exists
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return JsonResponse({
                'error': f'Campaign {campaign_id} not found'
            }, status=404)
        
        # Record spend asynchronously
        task = record_spend.delay(campaign_id, amount, spent_at)
        
        return JsonResponse({
            'message': 'Spend recorded successfully',
            'task_id': task.id,
            'campaign_id': campaign_id,
            'amount': amount,
            'status': 'accepted'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    except ValueError as e:
        return JsonResponse({
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in record_spend_api: {e}")
        return JsonResponse({
            'error': 'An error occurred while recording the spend'
        }, status=400)


@require_http_methods(["GET"])
def budget_status_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to check budget status for brands.
    
    Optional query parameters:
    - brand_id: Get status for specific brand
    """
    try:
        budget_service = BudgetService()
        
        # Get brand_id from query parameters
        brand_id_param = request.GET.get('brand_id')
        
        if brand_id_param:
            # Get status for specific brand
            brand_id = int(brand_id_param)
            try:
                brand_results = budget_service.check_brand_budget(brand_id)
                return JsonResponse({
                    'status': 'success',
                    'brand': dict(brand_results)
                })
            except ValueError as e:
                return JsonResponse({
                    'error': str(e)
                }, status=404)
        else:
            # Get summary for all brands
            summary_results = budget_service.get_budget_summary()
            return JsonResponse({
                'status': 'success',
                'summary': dict(summary_results)
            })
            
    except ValueError as e:
        return JsonResponse({
            'error': f'Invalid brand_id: {e}'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in budget_status_api: {e}")
        return JsonResponse({
            'error': 'An error occurred while checking budget status'
        }, status=400)


@require_http_methods(["GET"])
def dayparting_status_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to check dayparting status for campaigns.
    
    Optional query parameters:
    - campaign_id: Get status for specific campaign
    """
    try:
        dayparting_service = DaypartingService()
        
        # Get campaign_id from query parameters
        campaign_id_param = request.GET.get('campaign_id')
        
        if campaign_id_param:
            # Get status for specific campaign
            campaign_id = int(campaign_id_param)
            try:
                campaign_results = dayparting_service.update_campaign_dayparting(campaign_id)
                return JsonResponse({
                    'status': 'success',
                    'campaign': dict(campaign_results)
                })
            except ValueError as e:
                return JsonResponse({
                    'error': str(e)
                }, status=404)
        else:
            # Get summary for all campaigns
            summary_results = dayparting_service.get_dayparting_summary()
            return JsonResponse({
                'status': 'success',
                'summary': dict(summary_results)
            })
            
    except ValueError as e:
        return JsonResponse({
            'error': f'Invalid campaign_id: {e}'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in dayparting_status_api: {e}")
        return JsonResponse({
            'error': 'An error occurred while checking dayparting status'
        }, status=400) 
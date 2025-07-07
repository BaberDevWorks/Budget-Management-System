# Budget Management System - Pseudo-Code

## Data Models

### Brand Model
```
Brand:
  - id: Primary Key
  - name: String (Brand name)
  - daily_budget: Decimal (Daily spending limit)
  - monthly_budget: Decimal (Monthly spending limit)
  - daily_spend: Decimal (Current daily spend, default 0)
  - monthly_spend: Decimal (Current monthly spend, default 0)
  - is_active: Boolean (Brand status)
  - created_at: DateTime
  - updated_at: DateTime
```

### Campaign Model
```
Campaign:
  - id: Primary Key
  - brand: Foreign Key -> Brand
  - name: String (Campaign name)
  - is_active: Boolean (Campaign status)
  - is_paused_by_budget: Boolean (Budget-based pause status)
  - is_paused_by_dayparting: Boolean (Dayparting-based pause status)
  - created_at: DateTime
  - updated_at: DateTime
```

### Spend Model
```
Spend:
  - id: Primary Key
  - campaign: Foreign Key -> Campaign
  - amount: Decimal (Spend amount)
  - spent_at: DateTime (When the spend occurred)
  - created_at: DateTime
```

### DaypartingSchedule Model
```
DaypartingSchedule:
  - id: Primary Key
  - campaign: Foreign Key -> Campaign
  - day_of_week: Integer (0=Monday, 6=Sunday)
  - start_time: Time (Campaign start time)
  - end_time: Time (Campaign end time)
  - is_active: Boolean
```

## Key Logic Components

### 1. Spend Tracking Logic
```
FUNCTION record_spend(campaign_id, amount, timestamp):
  1. Create new Spend record
  2. Update brand's daily_spend += amount
  3. Update brand's monthly_spend += amount
  4. Check if brand exceeds daily/monthly budgets
  5. If exceeded, pause all brand campaigns (set is_paused_by_budget = True)
  6. Log the spend and any budget violations
```

### 2. Budget Enforcement Logic
```
FUNCTION check_budget_limits():
  FOR each active brand:
    IF brand.daily_spend >= brand.daily_budget:
      Pause all brand campaigns (budget reason)
    ELIF brand.monthly_spend >= brand.monthly_budget:
      Pause all brand campaigns (budget reason)
    ELSE:
      Reactivate campaigns paused by budget (if within dayparting)
```

### 3. Dayparting Logic
```
FUNCTION enforce_dayparting():
  current_time = get_current_time()
  current_day = get_current_day_of_week()
  
  FOR each campaign with dayparting schedules:
    is_in_dayparting_window = False
    
    FOR each schedule of the campaign:
      IF schedule.day_of_week == current_day:
        IF schedule.start_time <= current_time <= schedule.end_time:
          is_in_dayparting_window = True
          BREAK
    
    IF is_in_dayparting_window AND NOT campaign.is_paused_by_budget:
      campaign.is_paused_by_dayparting = False
      campaign.is_active = True
    ELSE:
      campaign.is_paused_by_dayparting = True
      campaign.is_active = False
```

### 4. Daily Reset Logic
```
FUNCTION daily_reset():
  1. Reset all brands' daily_spend to 0
  2. FOR each brand:
     - IF monthly_spend < monthly_budget:
       - Reactivate campaigns paused by budget
       - Apply dayparting rules to determine final status
     - ELSE:
       - Keep campaigns paused due to monthly budget
  3. Log daily reset completion
```

### 5. Monthly Reset Logic
```
FUNCTION monthly_reset():
  1. Reset all brands' monthly_spend to 0
  2. Reset all brands' daily_spend to 0
  3. FOR each brand:
     - Reactivate all campaigns paused by budget
     - Apply dayparting rules to determine final status
  4. Log monthly reset completion
```

## Celery Task Schedule

### Periodic Tasks
```
1. check_budgets_and_dayparting:
   - Frequency: Every 15 minutes
   - Purpose: Monitor budget limits and dayparting windows
   - Actions: Run budget enforcement and dayparting logic

2. daily_reset_task:
   - Frequency: Daily at 00:00
   - Purpose: Reset daily budgets and reactivate campaigns
   - Actions: Reset daily spends, reactivate eligible campaigns

3. monthly_reset_task:
   - Frequency: Monthly on 1st day at 00:00
   - Purpose: Reset monthly budgets and reactivate campaigns
   - Actions: Reset monthly spends, reactivate all eligible campaigns

4. cleanup_old_spends:
   - Frequency: Weekly
   - Purpose: Archive old spend records for performance
   - Actions: Move old spend records to archive table
```

## System Workflow

### Daily Operations
1. **Morning (00:00)**: Daily reset task runs
2. **Every 15 minutes**: Budget and dayparting check
3. **Real-time**: Spend tracking when ads run
4. **Evening**: Campaigns naturally pause due to dayparting

### Monthly Operations
1. **1st of month (00:00)**: Monthly reset task runs
2. **Continuous**: Daily operations continue as normal

### Budget Violation Response
1. **Immediate**: Pause all brand campaigns
2. **Next period**: Automatic reactivation if budget allows
3. **Logging**: All budget violations logged for reporting

## Error Handling & Edge Cases

### Concurrent Spend Updates
- Use database transactions to prevent race conditions
- Implement atomic updates for budget calculations

### System Downtime Recovery
- Graceful handling of missed periodic tasks
- Catchup logic for missed dayparting windows

### Data Integrity
- Validation of spend amounts (must be positive)
- Validation of budget limits (must be positive)
- Validation of dayparting schedules (start < end time) 
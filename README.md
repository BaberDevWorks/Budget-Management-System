# Django + Celery Budget Management System

A comprehensive budget management system for advertising agencies built with Django and Celery. This system tracks daily and monthly ad spend, automatically controls campaign activation based on budget limits, and enforces dayparting schedules.

## Features

- **Budget Tracking**: Real-time monitoring of daily and monthly spend against budgets
- **Automatic Campaign Control**: Campaigns are automatically paused when budgets are exceeded
- **Dayparting**: Time-based campaign scheduling (campaigns run only during specified hours)
- **Periodic Resets**: Automatic daily and monthly budget resets with campaign reactivation
- **Admin Interface**: Full-featured Django admin for managing brands, campaigns, and schedules
- **API Endpoints**: REST API for recording spend and checking status
- **Static Typing**: Complete type coverage with mypy for maintainability
- **Background Processing**: Celery tasks for all periodic operations

## Data Models

### Brand
- **Purpose**: Represents advertising brands with budget limits
- **Key Fields**: `name`, `daily_budget`, `monthly_budget`, `daily_spend`, `monthly_spend`, `is_active`
- **Relationships**: One-to-many with Campaigns

### Campaign
- **Purpose**: Represents individual advertising campaigns
- **Key Fields**: `name`, `is_active`, `is_paused_by_budget`, `is_paused_by_dayparting`
- **Relationships**: Many-to-one with Brand, one-to-many with Spends and DaypartingSchedules

### Spend
- **Purpose**: Records individual ad spend transactions
- **Key Fields**: `amount`, `spent_at`
- **Relationships**: Many-to-one with Campaign

### DaypartingSchedule
- **Purpose**: Defines time windows when campaigns can run
- **Key Fields**: `day_of_week`, `start_time`, `end_time`, `is_active`
- **Relationships**: Many-to-one with Campaign

## System Workflow

### Daily Operations
1. **00:00 UTC**: Daily reset task runs
   - Resets all brand daily spend to $0
   - Reactivates campaigns if monthly budget allows
   - Applies dayparting rules to determine final status

2. **Every 15 minutes**: Budget and dayparting check
   - Monitors all brand budgets
   - Pauses campaigns if limits exceeded
   - Updates campaign status based on dayparting schedules

3. **Real-time**: Spend tracking
   - New spend records update brand totals
   - Immediate budget violation checks
   - Automatic campaign pausing if needed

### Monthly Operations
1. **1st of month, 00:00 UTC**: Monthly reset task runs
   - Resets both daily and monthly spend to $0
   - Reactivates all campaigns paused by budget
   - Applies dayparting rules for final status

### Budget Violation Response
1. When a brand exceeds daily or monthly budget:
   - All campaigns for that brand are immediately paused
   - `is_paused_by_budget` flag is set to `True`
   - Campaign remains paused until next reset period

2. When budget is available again:
   - `is_paused_by_budget` flag is cleared
   - Campaign activation depends on dayparting rules
   - Only campaigns within dayparting windows become active

## Tech Stack

- **Backend**: Django 5.0.7 with PostgreSQL/SQLite
- **Task Queue**: Celery 5.3.7 with Redis
- **Type Checking**: mypy with strict configuration
- **Database**: PostgreSQL (production) / SQLite (development)
- **Caching/Broker**: Redis

## Installation & Setup

### 🐳 Option 1: Docker Setup (Recommended)

**One-command setup that starts everything automatically!**

✅ **Why choose Docker?**
- No need to install PostgreSQL, Redis, or manage multiple terminals
- All services start with one command
- Consistent environment across different systems
- Includes monitoring tools (Flower) out of the box

#### Prerequisites
- Docker and Docker Compose installed

#### Quick Start
```bash
# Clone and start everything with one command
git clone <repository-url>
cd budget-management-system
docker-compose up --build
```

This automatically starts:
- PostgreSQL Database (port 5432)
- Redis (port 6379) 
- Django Web Application (port 8000)
- Celery Worker (background tasks)
- Celery Beat (scheduled tasks)
- Flower (Celery monitoring - port 5555)

#### Access the Application
- **Main App**: http://localhost:8000
- **Admin Interface**: http://localhost:8000/admin/
- **Celery Monitoring**: http://localhost:5555

#### Management Commands with Docker
```bash
# Create superuser
docker-compose exec web python manage.py createsuperuser

# Load sample data
docker-compose exec web python manage.py load_sample_data --brands 5 --campaigns-per-brand 3

# View logs
docker-compose logs

# Stop everything
docker-compose down
```

See [DOCKER_SETUP.md](DOCKER_SETUP.md) for detailed Docker documentation.

---

### 💻 Option 2: Manual Setup

**For developers who prefer traditional setup or need custom configurations.**

#### Prerequisites
- Python 3.9+
- PostgreSQL or SQLite
- Redis Server

#### 1. Clone the Repository
```bash
git clone <repository-url>
cd budget-management-system
```

#### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 4. Environment Configuration
Copy `env.example` to `.env` and configure:
```bash
cp env.example .env
```

Edit `.env` with your settings:
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
DB_NAME=budget_management
DB_USER=postgres
DB_PASSWORD=postgres
CELERY_BROKER_URL=redis://localhost:6379/0
```

#### 5. Database Setup
```bash
# Apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Load sample data (optional)
python manage.py load_sample_data --brands 5 --campaigns-per-brand 3
```

#### 6. Start Services

**Terminal 1 - Django Development Server:**
```bash
python manage.py runserver
```

**Terminal 2 - Celery Worker:**
```bash
celery -A budget_management worker --loglevel=info
```

**Terminal 3 - Celery Beat (Scheduler):**
```bash
celery -A budget_management beat --loglevel=info
```

**Terminal 4 - Redis Server:**
```bash
redis-server
```

> **💡 Tip**: Instead of managing 4 terminals, you can use the Docker setup: `docker-compose up --build`

## Usage

### Admin Interface
1. Access Django Admin at `http://localhost:8000/admin/`
2. Login with superuser credentials
3. Manage brands, campaigns, and dayparting schedules

### API Endpoints

#### Record Spend
```bash
POST /campaigns/api/record-spend/
Content-Type: application/json

{
    "campaign_id": 1,
    "amount": 50.00,
    "spent_at": "2023-12-01T10:00:00Z"  # Optional
}
```

#### Check Budget Status
```bash
GET /campaigns/api/budget-status/
GET /campaigns/api/budget-status/?brand_id=1
```

#### Check Dayparting Status
```bash
GET /campaigns/api/dayparting-status/
GET /campaigns/api/dayparting-status/?campaign_id=1
```

### Management Commands

#### Manual Budget Check
```bash
python manage.py check_budgets
python manage.py check_budgets --brand-id 1
python manage.py check_budgets --dry-run
```

#### Load Sample Data
```bash
python manage.py load_sample_data
python manage.py load_sample_data --clear --brands 10
```

## Celery Tasks

### Periodic Tasks
- `check_budgets_and_dayparting`: Every 15 minutes
- `daily_reset_task`: Daily at 00:00 UTC
- `monthly_reset_task`: 1st of month at 00:00 UTC
- `cleanup_old_spends`: Weekly on Monday at 02:00 UTC

### Manual Tasks
- `record_spend`: Record new spend (called via API)
- `update_campaign_dayparting`: Update single campaign
- `force_brand_reset`: Manual brand reset

## Type Checking

The project uses mypy for static type checking:

```bash
# Run type checking
mypy .

# Check specific files
mypy campaigns/models.py
mypy campaigns/tasks.py
```

Configuration is in `mypy.ini` with strict settings enabled.

## Project Structure

```
budget-management-system/
├── manage.py
├── requirements.txt
├── mypy.ini
├── env.example
├── README.md
├── PSEUDO_CODE.md
├── budget_management/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── celery.py
└── campaigns/
    ├── __init__.py
    ├── apps.py
    ├── models.py
    ├── views.py
    ├── urls.py
    ├── admin.py
    ├── services.py
    ├── tasks.py
    └── management/
        └── commands/
            ├── check_budgets.py
            └── load_sample_data.py
```

## Testing

### Manual Testing
1. Load sample data: `python manage.py load_sample_data`
2. Check admin interface for created brands and campaigns
3. Use API endpoints to record spend
4. Verify budget limits trigger campaign pausing
5. Test dayparting by creating schedules

### Budget Testing
```bash
# Check current budget status
python manage.py check_budgets --dry-run

# Force budget check
python manage.py check_budgets --verbose
```

## Architecture Decisions

### Database Design
- Separate spend tracking from budget totals for audit trail
- Atomic transactions for budget updates to prevent race conditions
- Indexes on frequently queried fields (campaign, spent_at)

### Task Processing
- Celery for reliable background processing
- Separate queues for different task types
- Retry mechanisms with exponential backoff
- Task expiration to prevent stale tasks

### Type Safety
- Comprehensive type hints throughout codebase
- mypy configuration for strict checking
- Proper typing for Django models and views

## Assumptions & Simplifications

1. **Currency**: All amounts assumed to be in USD
2. **Timezone**: System operates in UTC
3. **Budget Periods**: Daily budgets reset at 00:00 UTC, monthly on 1st
4. **Dayparting**: Based on UTC timezone
5. **Campaign Overlap**: Campaigns can have overlapping dayparting schedules
6. **Spend Recording**: Assumes external systems will call API to record spend
7. **Data Retention**: Old spend records cleaned up after 90 days

## Future Enhancements

1. **Multi-currency Support**: Handle different currencies
2. **Timezone Awareness**: Brand-specific timezones
3. **Advanced Reporting**: Detailed spend analytics
4. **Notifications**: Email/SMS alerts for budget violations
5. **API Authentication**: Secure API endpoints
6. **Audit Trail**: Track all budget and campaign changes
7. **Machine Learning**: Predictive budget management

## License

This project is licensed under the MIT License.
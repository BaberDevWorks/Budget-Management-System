# Docker Setup Guide

This guide will help you run the entire Budget Management System with a single command using Docker Compose.

## Prerequisites

- Docker installed on your system
- Docker Compose installed on your system

## Quick Start

### 1. Start All Services

Run this single command to start everything:

```bash
docker-compose up --build
```

This will start:
- **PostgreSQL Database** (port 5432)
- **Redis** (port 6379)
- **Django Web Application** (port 8000)
- **Celery Worker** (background task processing)
- **Celery Beat** (scheduled tasks)
- **Flower** (Celery monitoring on port 5555)

### 2. Access the Application

Once all services are running, you can access:

- **Main Application**: http://localhost:8000
- **Django Admin**: http://localhost:8000/admin/
- **Celery Monitoring (Flower)**: http://localhost:5555

### 3. Stop All Services

To stop all services:

```bash
docker-compose down
```

To stop and remove volumes (clears database data):

```bash
docker-compose down -v
```

## Development Commands

### View Logs

```bash
# View all service logs
docker-compose logs

# View specific service logs
docker-compose logs web
docker-compose logs celery
docker-compose logs celery-beat
```

### Run Django Commands

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic

# Run Django shell
docker-compose exec web python manage.py shell
```

### Database Management

```bash
# Connect to PostgreSQL
docker-compose exec db psql -U budget_user -d budget_management

# Reset database (removes all data)
docker-compose down -v
docker-compose up --build
```

### Celery Management

```bash
# Monitor Celery tasks
docker-compose exec celery celery -A budget_management status

# Inspect active tasks
docker-compose exec celery celery -A budget_management inspect active
```

## Service Details

### Web Application
- **Port**: 8000
- **Auto-reload**: Enabled for development
- **Migrations**: Run automatically on startup
- **Static files**: Collected automatically

### Database
- **Type**: PostgreSQL 15
- **Database**: budget_management
- **User**: budget_user
- **Password**: budget_password
- **Port**: 5432

### Redis
- **Port**: 6379
- **Used for**: Celery message broker and result backend

### Celery Worker
- **Purpose**: Process background tasks
- **Log level**: INFO
- **Auto-restart**: Enabled

### Celery Beat
- **Purpose**: Schedule periodic tasks
- **Log level**: INFO
- **Auto-restart**: Enabled

### Flower
- **Purpose**: Monitor Celery tasks
- **Port**: 5555
- **Features**: Real-time task monitoring, worker statistics

## Environment Variables

The Docker setup uses these environment variables:

```bash
# Database
DB_NAME=budget_management
DB_USER=budget_user
DB_PASSWORD=budget_password
DB_HOST=db
DB_PORT=5432

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Django
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
```

## Troubleshooting

### Services won't start
- Make sure Docker is running
- Check that ports 5432, 6379, 8000, and 5555 are not in use
- Try rebuilding: `docker-compose up --build --force-recreate`

### Database connection issues
- Wait for the database to be ready (health checks are configured)
- Check logs: `docker-compose logs db`

### Celery tasks not running
- Check worker logs: `docker-compose logs celery`
- Check Redis connection: `docker-compose logs redis`
- Visit Flower dashboard: http://localhost:5555

### Permission issues
- The application runs as a non-root user inside containers
- File permissions are handled automatically

## Production Considerations

For production deployment:

1. Change database credentials
2. Set `DEBUG=False`
3. Configure proper `ALLOWED_HOSTS`
4. Use environment variables for secrets
5. Set up proper logging
6. Consider using managed services for PostgreSQL and Redis

## Stopping Development

When you're done developing:

```bash
# Stop services but keep data
docker-compose down

# Stop services and remove all data
docker-compose down -v

# Remove built images (optional)
docker system prune
``` 
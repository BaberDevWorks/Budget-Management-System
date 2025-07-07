"""
Django app configuration for the campaigns app.
"""
from django.apps import AppConfig


class CampaignsConfig(AppConfig):
    """Configuration for the campaigns app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'campaigns'
    verbose_name = 'Campaign Budget Management'
    
    def ready(self) -> None:
        """
        Called when the app is ready.
        Import signal handlers here to ensure they are connected.
        """
        # Import signal handlers if any
        # from . import signals
        pass
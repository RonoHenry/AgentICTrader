from django.conf import settings

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': settings.DATABASE_CONFIG['name'],
        'USER': settings.DATABASE_CONFIG['user'],
        'PASSWORD': settings.DATABASE_CONFIG['password'],
        'HOST': settings.DATABASE_CONFIG['host'],
        'PORT': settings.DATABASE_CONFIG['port'],
    },
    'timeseries': {
        'ENGINE': 'django_influxdb',
        'NAME': 'agentic_trader_timeseries',
        'HOST': settings.INFLUXDB_CONFIG['host'],
        'PORT': settings.INFLUXDB_CONFIG['port'],
        'TOKEN': settings.INFLUXDB_CONFIG['token'],
        'ORG': settings.INFLUXDB_CONFIG['org'],
    }
}

# Database Routers
class TimeSeriesRouter:
    """
    Router to send time-series data to InfluxDB
    """
    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'trader' and model._meta.model_name in ['candle', 'tick']:
            return 'timeseries'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'trader' and model._meta.model_name in ['candle', 'tick']:
            return 'timeseries'
        return 'default'

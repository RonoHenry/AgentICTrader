from pathlib import Path
from decouple import config

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Deriv API settings
DERIV_CONFIG = {
    'app_id': config('DERIV_APP_ID'),
    'api_token': config('DERIV_API_TOKEN'),
    'oauth_redirect_url': config('DERIV_OAUTH_REDIRECT_URL'),
    'demo_mode': config('DERIV_DEMO_MODE', default=True, cast=bool),
}

# Database settings
DATABASE_CONFIG = {
    'name': config('DB_NAME'),
    'user': config('DB_USER'),
    'password': config('DB_PASSWORD'),
    'host': config('DB_HOST'),
    'port': config('DB_PORT', cast=int),
}

# Redis settings
REDIS_CONFIG = {
    'host': config('REDIS_HOST'),
    'port': config('REDIS_PORT', cast=int),
}

# Security settings
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

# Environment
ENVIRONMENT = config('ENVIRONMENT', default='production')

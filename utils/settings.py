import sys
import os
import logging
import datetime
import redis
import django.http
import re
from mongoengine import connect

SEND_ERROR_MAILS = False#True
D_OCEAN_REDIS_POOL = redis.ConnectionPool(host="172.21.1.155", port=6379, db=0)

# ===========================
# = Directory Declaractions =
# ===========================
CURRENT_DIR   = os.path.dirname(__file__)
LOG_FILE      = os.path.join(CURRENT_DIR, 'logs/django_rss.log')
UTILS_ROOT    = os.path.join(CURRENT_DIR, 'utils')
VENDOR_ROOT   = os.path.join(CURRENT_DIR, 'vendor')

# ==============
# = PYTHONPATH =
# ==============

if '/utils' not in ' '.join(sys.path):
    sys.path.append(UTILS_ROOT)

if '/vendor' not in ' '.join(sys.path):
    sys.path.append(VENDOR_ROOT)


DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    # ('Xinyan Lu', 'luxinyan@outlook.com'),
    ('Chen Yiyu','515822895@qq.com'),
)

# These two properties do not affect
NEWSBLUR_URL = 'http://www.dcd.zju.edu.cn'
SERVER_NAME  = 'dcd03'

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        # Add 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'mydb',
        # Or path to database file if using sqlite3.
        # The following settings are not used with sqlite3:
        'USER': 'postgres',
        'PASSWORD': 'postgres1234',
        'HOST': 'localhost',                      # Empty for localhost through domain sockets or '127.0.0.1' for localhost through TCP.
        'PORT': '',                      # Set to empty string for default.
    }
}

# ==========
# = Celery =
# ==========

import djcelery
djcelery.setup_loader()
CELERY_ROUTES = {
    "work-queue": {
        "queue": "work_queue",
        "binding_key": "work_queue"
    },
    "new-feeds": {
        "queue": "new_feeds",
        "binding_key": "new_feeds"
    },
    "push-feeds": {
        "queue": "push_feeds",
        "binding_key": "push_feeds"
    },
    "update-feeds": {
        "queue": "update_feeds",
        "binding_key": "update_feeds"
    },
    "beat-tasks": {
        "queue": "beat_tasks",
        "binding_key": "beat_tasks"
    },
    "update-feed-images": {
        "queue": "update_feed_images",
        "binding_key": "update_feed_images"
    },
    "net-monitor-task": {
        "queue": "beat_tasks",
        "binding_key": "net_monitor_task"
    },
}
CELERY_QUEUES = {
    "work_queue": {
        "exchange": "work_queue",
        "exchange_type": "direct",
        "binding_key": "work_queue",
    },
    "new_feeds": {
        "exchange": "new_feeds",
        "exchange_type": "direct",
        "binding_key": "new_feeds"
    },
    "push_feeds": {
        "exchange": "push_feeds",
        "exchange_type": "direct",
        "binding_key": "push_feeds"
    },
    "update_feeds": {
        "exchange": "update_feeds",
        "exchange_type": "direct",
        "binding_key": "update_feeds"
    },
    "beat_tasks": {
        "exchange": "beat_tasks",
        "exchange_type": "direct",
        "binding_key": "beat_tasks"
    },
    "beat_feeds_task": {
        "exchange": "beat_feeds_task",
        "exchange_type": "direct",
        "binding_key": "beat_feeds_task"
    },
    "update_feed_images": {
        "exchange": "update_feed_images",
        "exchange_type": "direct",
        "binding_key": "update_feed_images"
    },
}
CELERY_DEFAULT_QUEUE = "work_queue"

CELERYD_PREFETCH_MULTIPLIER = 1
CELERY_IMPORTS              = ("apps.rss_feeds.tasks",)
                               # "apps.social.tasks",
                               # "apps.reader.tasks",
                               # "apps.feed_import.tasks",
                               # "apps.statistics.tasks",)
CELERYD_CONCURRENCY         = 3
CELERY_IGNORE_RESULT        = True
CELERY_ACKS_LATE            = True # Retry if task fails
CELERYD_MAX_TASKS_PER_CHILD = 10
CELERYD_TASK_TIME_LIMIT     = 12 * 30
CELERY_DISABLE_RATE_LIMITS  = True
SECONDS_TO_DELAY_CELERY_EMAILS = 60

CELERYBEAT_SCHEDULE = {
    'task-feeds': {
        'task': 'task-feeds',
        'schedule': datetime.timedelta(minutes=1),
        'options': {'queue': 'beat_feeds_task'},
    },
    # Add by Dapeng Jiang(jdpdyx@126.com)
    'net-monitor-task' : {
        'task': 'net-monitor-task',
        'schedule': datetime.timedelta(minutes=1),
        'options': {'queue': 'beat_tasks'},
    },
    # Modified by Xinyan Lu (luxinyan@outlook.com): these functions are not needed
    # 'freshen-homepage': {
    #     'task': 'freshen-homepage',
    #     'schedule': datetime.timedelta(hours=1),
    #     'options': {'queue': 'beat_tasks'},
    # },
    # 'collect-stats': {
    #     'task': 'collect-stats',
    #     'schedule': datetime.timedelta(minutes=1),
    #     'options': {'queue': 'beat_tasks'},
    # },
    # The 'collect-feedback' is commented by the original author
#    'collect-feedback': {
#        'task': 'collect-feedback',
#        'schedule': datetime.timedelta(minutes=1),
#        'options': {'queue': 'beat_tasks'},
#    },

    # 'share-popular-stories': {
    #     'task': 'share-popular-stories',
    #     'schedule': datetime.timedelta(minutes=10),
    #     'options': {'queue': 'beat_tasks'},
    # },
    # 'clean-analytics': {
    #     'task': 'clean-analytics',
    #     'schedule': datetime.timedelta(hours=12),
    #     'options': {'queue': 'beat_tasks'},
    # },
    # 'premium-expire': {
    #     'task': 'premium-expire',
    #     'schedule': datetime.timedelta(hours=24),
    #     'options': {'queue': 'beat_tasks'},
    # },
    # 'activate-next-new-user': {
    #     'task': 'activate-next-new-user',
    #     'schedule': datetime.timedelta(minutes=1),
    #     'options': {'queue': 'beat_tasks'},
    # },
}
#=====================================
#= Add by SongJun=
CELERY_SEND_TASK_ERROR_EMAILS = SEND_ERROR_MAILS
#=====================================

# =========
# = Redis =
# =========

REDIS = {
    # 'host': 'redis1',
    #'host': 'localhost',
    'host': 'localhost',
}
REDIS_PUBSUB = {
    # 'host': 'redis2',
    #'host': 'localhost',
    'host': 'localhost',
}
REDIS_STORY = {
    # 'host': 'redis3',
    #'host': 'localhost',
    'host': 'localhost',
}
CELERY_REDIS_DB = 4
SESSION_REDIS_DB = 5

# =========
# = Redis =
# =========

BROKER_BACKEND = "redis"
BROKER_URL = "redis://%s:6379/%s" % (REDIS['host'], CELERY_REDIS_DB)
CELERY_RESULT_BACKEND = BROKER_URL
SESSION_REDIS_HOST = REDIS['host']

CACHES = {
    'default': {
        'BACKEND': 'redis_cache.RedisCache',
        'LOCATION': '%s:6379' % REDIS['host'],
        'OPTIONS': {
            'DB': 6,
            'PARSER_CLASS': 'redis.connection.HiredisParser'
        },
    },
}

# =========
# = Redis =
# =========

REDIS_POOL               = redis.ConnectionPool(host=REDIS['host'], port=6379, db=0)
REDIS_ANALYTICS_POOL     = redis.ConnectionPool(host=REDIS['host'], port=6379, db=2)
REDIS_STATISTICS_POOL    = redis.ConnectionPool(host=REDIS['host'], port=6379, db=3)
REDIS_FEED_POOL          = redis.ConnectionPool(host=REDIS['host'], port=6379, db=4)
REDIS_SESSION_POOL       = redis.ConnectionPool(host=REDIS['host'], port=6379, db=5)
REDIS_NETWORK_POOL       = redis.ConnectionPool(host=REDIS['host'], port=6379, db=6)
# REDIS_CACHE_POOL       = redis.ConnectionPool(host=REDIS['host'], port=6379, db=6) # Duped in CACHES
REDIS_PUBSUB_POOL        = redis.ConnectionPool(host=REDIS_PUBSUB['host'], port=6379, db=0)
REDIS_STORY_HASH_POOL    = redis.ConnectionPool(host=REDIS_STORY['host'], port=6379, db=1)
# REDIS_STORY_HASH_POOL2 = redis.ConnectionPool(host=REDIS['host'], port=6379, db=8)

# ===================
# = Network Monitor =
# ===================
REDIS_NETWORK_LOG_MAX = 1500
REDIS_NETWORK_LOG_NAME= "network_log"

# =========
# = Mongo =
# =========

MONGO_DB = {
    'host': '172.21.1.155:27017',
    'name': 'newszeit',
}
MONGO_ANALYTICS_DB = {
    'host': '172.21.1.155:27017',
    'name': 'nbanalytics',
}

MONGO_DB_DEFAULTS = {
    'name': 'newszeit',
    'host': '172.21.1.155:27017',
    'alias': 'default',
}
MONGO_ANALYTICS_DB_DEFAULTS = {
    'name': 'nbanalytics',
    'host': '172.21.1.155:27017',
    'alias': 'nbanalytics',
}
MONGO_DB = dict(MONGO_DB_DEFAULTS, **MONGO_DB)

# if MONGO_DB.get('read_preference', pymongo.ReadPreference.PRIMARY) != pymongo.ReadPreference.PRIMARY:
#     MONGO_PRIMARY_DB = MONGO_DB.copy()
#     MONGO_PRIMARY_DB.update(read_preference=pymongo.ReadPreference.PRIMARY)
#     MONGOPRIMARYDB = connect(MONGO_PRIMARY_DB.pop('name'), **MONGO_PRIMARY_DB)
# else:
#     MONGOPRIMARYDB = MONGODB
MONGODB = connect(MONGO_DB.pop('name'), **MONGO_DB)
MONGO_ANALYTICS_DB = dict(MONGO_ANALYTICS_DB_DEFAULTS, **MONGO_ANALYTICS_DB)
MONGOANALYTICSDB = connect(MONGO_ANALYTICS_DB.pop('name'), **MONGO_ANALYTICS_DB)

# =================
# = Elasticsearch =
# =================

ELASTICSEARCH_HOSTS = ['localhost:9200']

# ===========
# = FastDFS =
# ===========
# Should be a absolute path

FDFS_CLIENT_CONF_PATH = os.path.join(CURRENT_DIR, 'conf/fdfs/client.conf')
# bind the ip and port
FDFS_HTTP_SERVER = 'http://172.21.1.155:8090/'

# ===============
# = AWS Backing =
# ===============

BACKED_BY_AWS = {
    'pages_on_s3': False,
    'icons_on_s3': False,
}

# Hosts/domain names that are valid for this site; required if DEBUG is False
# See https://docs.djangoproject.com/en/1.5/ref/settings/#allowed-hosts
ALLOWED_HOSTS = []

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'Asia/Shanghai'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
# USE_L10N = False

# If you set this to False, Django will not use timezone-aware datetimes.
# USE_TZ = False

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/var/www/example.com/media/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://example.com/media/", "http://media.example.com/"
MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/var/www/example.com/static/"
STATIC_ROOT   = ''

# URL prefix for static files.
# Example: "http://example.com/static/", "http://static.example.com/"
STATIC_URL = '/static/'
# Additional locations of static files
STATICFILES_DIRS = (
    os.path.join(CURRENT_DIR, 'static'),
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'lb-o1_oa4pkb2z03j)p&&i0(e3a-_ys297j#1#q23k3blz80$4'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Uncomment the next line for simple clickjacking protection:
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'wsgi.application'

TEMPLATE_DIRS = (
    os.path.join(CURRENT_DIR, 'templates'),
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

INSTALLED_APPS = (
    'django_extensions',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',
    'djcelery',
    'apps.rss_feeds',
    'apps.search',
    'apps.statistics',    
    'utils',
    'vendor',
)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOG_LEVEL = logging.DEBUG
LOG_TO_STREAM = False

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[%(asctime)-12s] %(message)s',
            'datefmt': '%b %d %H:%M:%S'
        },
        'simple': {
            'format': '%(message)s'
        },
    },
    'handlers': {
        'null': {
            'level':'DEBUG',
            'class':'django.utils.log.NullHandler',
        },
        'console':{
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        'log_file':{
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_FILE,
            'maxBytes': 16777216, # 16megabytes
            'formatter': 'verbose'
        },
        # 'mail_admins': {
        #     'level': 'ERROR',
        #     'class': 'django.utils.log.AdminEmailHandler',
        #     'filters': ['require_debug_false'],
        #     'include_html': True,
        # }
        # Modified By Xinyan Lu: no mail notice
        'log_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_FILE+'.ERROR.log',
            'maxBytes': 16777216, # 16megabytes
            'formatter': 'verbose',
            # without this line, there would be a warning. Xinyan Lu
            #'filters': ['require_debug_false'],
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['console', 'log_file'],
            'level': 'ERROR',
            'propagate': True,
        },
        'django.db.backends': {
            'handlers': ['null'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'newsblur': {
            'handlers': ['console', 'log_file','log_error'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apps': {
            'handlers': ['log_file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
}

# !!! should be remove later
# ==========================
# = Miscellaneous Settings =
# ==========================

DAYS_OF_UNREAD          = 14
DAYS_OF_UNREAD_NEW      = 30
SUBSCRIBER_EXPIRE       = 2


#============================
#= COW Corss the Green Wall =
#============================
COW_PROXY_HANDLER = 'http://10.214.34.221:7777'

#=======================
#= Image URL Blacklist =
#=======================
IMAGE_URL_BLACKLIST = os.path.join(CURRENT_DIR,'conf/image_url_blacklist')

#=====================
#= Mail Notification =
#=====================
MAIL_HOST = "smtp.126.com"
MAIL_USER = "rss_feeds"
MAIL_PASS = "zjurss"
MAIL_POSTFIX = "126.com"
MAIL_NOTIFY_LIST = ['515822895@qq.com']
# MAIL_NOTIFY_LIST = ['songjun54cm@gmail.com','luxinyan@outlook.com']

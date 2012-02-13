import os, sys
sys.path.append('/usr/local/django')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehriimporter.settings'

import django.core.handlers.wsgi

application = django.core.handlers.wsgi.WSGIHandler()

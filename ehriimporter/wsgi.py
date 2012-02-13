import os, sys

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(PROJECT_ROOT, "../../../lib/python2.6/site-packages")))

os.environ['DJANGO_SETTINGS_MODULE'] = 'ehriimporter.settings'

import django.core.handlers.wsgi

application = django.core.handlers.wsgi.WSGIHandler()

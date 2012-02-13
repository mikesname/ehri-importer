import os, sys

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(PROJECT_ROOT))
sys.path.insert(0, os.path.abspath(os.path.join(PROJECT_ROOT, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(PROJECT_ROOT, "../../../lib/python2.6/site-packages")))

# Add temporary path for sqlaqubit module, which is pull as src from
# github 'cos it's not finished yet
sys.path.insert(0, os.path.abspath(os.path.join(PROJECT_ROOT, "../../../src/sqlaqubit")))


os.environ['DJANGO_SETTINGS_MODULE'] = 'ehriimporter.settings'

import django.core.handlers.wsgi

application = django.core.handlers.wsgi.WSGIHandler()

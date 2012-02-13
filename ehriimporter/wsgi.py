import os, sys

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(PROJECT_ROOT, "..")))

venv_path = os.path.abspath(os.path.join(PROJECT_ROOT, "../../../"))
activate_this = os.path.join(venv_path, "bin/activate_this.py")
execfile(activate_this, dict(__file__=activate_this))

os.environ['DJANGO_SETTINGS_MODULE'] = 'ehriimporter.settings'

import django.core.handlers.wsgi

application = django.core.handlers.wsgi.WSGIHandler()

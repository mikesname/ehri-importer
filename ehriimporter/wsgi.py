import os, sys

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_NAME = os.path.basename(PROJECT_ROOT)

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(PROJECT_ROOT, os.pardir)))

venv_path = os.path.abspath(os.path.join(PROJECT_ROOT, "../../../"))
activate_this = os.path.join(venv_path, "bin/activate_this.py")
execfile(activate_this, dict(__file__=activate_this))

sys.stderr.write("WSGI Python Path (Importer): %s\n" % sys.path)

os.environ['DJANGO_SETTINGS_MODULE'] = '%s.settings' % PROJECT_NAME

import django.core.handlers.wsgi

application = django.core.handlers.wsgi.WSGIHandler()

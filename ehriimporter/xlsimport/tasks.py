"""Importer long-running tasks."""

from django.conf import settings
from celery.task import Task
from xlsimport import importers

DBNAME = getattr(settings, "IMPORTER_QUBIT_DBNAME", "icaatom")
DBUSER = getattr(settings, "IMPORTER_QUBIT_DBUSER", "icaatom")
DBPASS = getattr(settings, "IMPORTER_QUBIT_DBPASS", "changeme")
USER = getattr(settings, "IMPORTER_QUBIT_USER", "mike")


class ImportXLSTask(Task):
    name = "xlsimport.ImportXSL"
    def run(self, importerklass, xlsfile):
        importer = getattr(importers, importerklass)(database=DBNAME, username=DBUSER, 
                    password=DBPASS, atomuser=USER)
        importer.validate(xlsfile)
        total = importer.num_rows()
        meta = dict(counter=0)
        def rowfunc(repo):
            meta["counter"] += 1
            self.update_state(state="PROGRESS", meta=dict(
                current=meta["counter"], total=total))
        importer.rowfunc = rowfunc
        importer.do(xlsfile)





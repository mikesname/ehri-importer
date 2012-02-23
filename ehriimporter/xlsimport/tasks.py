from celery.task import Task
from importers import xls as xlsi


class ImportXLSTask(Task):
    name = "xlsimport.ImportXSL"
    def run(self, xlsfile, user=None):
        importer = xlsi.XLSRepositoryImporter("icaatom", "icaatom", "changeme", atomuser=user)
        importer.validate(xlsfile)
        total = importer.num_rows()
        meta = dict(counter=0)
        def rowfunc(repo):
            meta["counter"] += 1
            self.update_state(state="PROGRESS", meta=dict(
                current=meta["counter"], total=total))
        importer.rowfunc = rowfunc
        importer.do(xlsfile)





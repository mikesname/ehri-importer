from celery.task import task
from importers import xls as xlsi

@task(ignore_result=True)
def import_xls(xlsfile, user=None):
    importer = xlsi.XLSRepositoryImporter("icaatom", "icaatom", "changeme", atomuser=user)
    importer.validate(xlsfile)
    total = importer.num_rows()
    logger = import_xls.get_logger()
    counter = 0
    def donefunc():        
        import_xls.update_state(state="PROGRESS", meta=dict(
            current=total, total=total))
    def rowfunc(repo):
        import sys
        sys.stderr.write("Imported: %s" % repo.identifier)
        logger = import_xls.get_logger()
        logger.info("Imported: %s", repo.identifier)
        import_xls.update_state(state="PROGRESS", meta=dict(
            current=counter, total=total))
    importer.donefunc = donefunc
    importer.rowfunc = rowfunc
    importer.do(xlsfile)




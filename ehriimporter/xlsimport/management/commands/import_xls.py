"""
Import repository information from a spreadsheet.
"""

from optparse import make_option

from django.core.management.base import BaseCommand, CommandError

from xlsimport.importers import xls

class Command(BaseCommand):
    """Import repositories from ICA Atom."""
    args = "<XLS file>"
    option_list = BaseCommand.option_list + (
        make_option(
                "-U",
                "--dbuser",
                action="store",
                dest="dbuser",
                default="icaatom",
                help="Database user"),
        make_option(
                "-p",
                "--dbpass",
                action="store",
                dest="dbpass",
                help="Database password"),
        make_option(
                "-H",
                "--dbhost",
                action="store",
                dest="dbhost",
                default="localhost",
                help="Database host name"),
        make_option(
                "-P",
                "--dbport",
                action="store",
                dest="dbport",
                help="Database port"),
        make_option(
                "-D",
                "--database",
                action="store",
                dest="database",
                default="icaatom",
                help="Database name"),
        make_option(
                "-u",
                "--user",
                action="store",
                dest="user",
                default="qubit",
                help="User to own imported records")
    )
    
    def handle(self, *args, **options):
        """Perform import."""
        if not args:
            raise CommandError("No XLS file given.")

        def donefunc():
            self.stderr.write("Done\n")
        def rowfunc(repo):
            self.stderr.write("Imported: %s\n" % repo.identifier)
        importer = xls.Repository(options["database"], options["dbuser"],
                options["dbpass"], options["dbhost"], options["dbport"], options["user"],
                rowfunc=rowfunc, donefunc=donefunc)
        importer.do(args[0])


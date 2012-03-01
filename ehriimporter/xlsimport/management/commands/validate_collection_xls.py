"""
Validate repository information from a spreadsheet.
"""

from django.core.management.base import BaseCommand, CommandError

from xlsimport import validators

class Command(BaseCommand):
    """Import collections to ICA Atom."""
    args = "<XLS file>"
    def handle(self, *args, **options):
        """Perform import."""
        if not args:
            raise CommandError("No XLS file given.")

        validator = validators.Collection()
        validator.validate(args[0])
        if validator.errors:
            for err in validator.errors:
                self.stderr.write("Line %-6d : %s\n" % err[0:2])



"""Class for validating an ISDIAH .xls file."""

import os
import re
import datetime
import logging as LOG
from ordereddict import OrderedDict
from dateutil import parser

import phpserialize
import xlrd
import yaml

from xlsimport import utils


class XLSError(Exception):
    """Something went wrong with XLS import."""

MAX_CHARFIELD_LENGTH = 255

ERROR_CODES = {
        u"bad_xls": u"Unable to open XLS file.",
        u"worksheet_not_found": u"Data worksheet must be the first sheet in the workbook.",
        u"unexpected_heading": u"Unexpected headings on worksheet",
        u"missing_heading": u"Heading not found on worksheet",
}


def split_multiple(multistr, sep=",,"):
    return [s for s in unicode(multistr).rsplit(sep) if s.strip()]


class XLSField(object):
    def __init__(self, name, unique=False, multiple=False,
            default=None, required=False, date=False,
            validate=False, i18n=False, type=None, help=None,
            choices=None):
        self.name = name
        self.unique = unique
        self.multiple = multiple
        self.default = default
        self.required = False
        self.i18n = i18n
        self.validate = False
        self.type = type
        self.limit = None
        self.help = help
        self.choices = choices

    def __unicode__(self):
        return self.name

    def __repr__(self):
        return "<XLSField: '%s'>" % self.name

class XLSSheetDefinition(object):
    def __init__(self, heading_row=0, fields=None):
        self.heading_row = heading_row
        self.fields = fields if fields is not None else []

    def load_yaml(self, filepath):
        self.fields = OrderedDict()
        with open(filepath, "r") as fp:
            data = yaml.load(fp)
            self.heading_row = data.get("heading_row", self.heading_row)
            for fielddef in data.get("fields", []):
                for name, fdef in fielddef.iteritems():
                    field = XLSField(name)
                    if fdef is not None:
                        for key, val in fdef.iteritems():
                            setattr(field, key, val)
                    self.fields[name] = field

    def names(self):
        return self.fields.keys()
    
    def unique(self):
        return [f for f in self.fields.values() if f.unique]

    def multiple(self):
        return [f for f in self.fields.values() if f.multiple]

    def i18n(self):
        return [f for f in self.fields.values() if f.i18n]

    def required(self):
        return [f for f in self.fields.values() if f.required]

    def date(self):
        return [f for f in self.fields.values() if f.type=="date"]

    def oftype(self, type):
        return [f for f in self.fields.values() if f.type==type]

    def limited(self):
        return [f for f in self.fields.values() if f.limit]

    def choices(self):
        return [f for f in self.fields.values() if f.choices is not None]


class XLSValidator(object):
    def __init__(self, definitions=None, raise_err=False):
        self.workbook = None
        self.sheet = None
        self.fielddef = XLSSheetDefinition()
        if definitions is not None:
            defpath = os.path.abspath(
                    os.path.join(
                        os.path.dirname(__file__),                        
                        "definitions", definitions))
            self.fielddef.load_yaml(defpath)
        
        self.raise_err = raise_err
        self.errors = []

    @property
    def HEADING_ROW(self):
        return self.fielddef.heading_row

    @property
    def HEADINGS(self):
        return self.fielddef.names()

    @property
    def UNIQUES(self):
        return [f.name for f in self.fielddef.unique()]

    @property
    def MULTIPLES(self):
        return [f.name for f in self.fielddef.multiple()]

    @property
    def REQUIRED(self):
        return [f.name for f in self.fielddef.required()]

    @property
    def DATES(self):
        return [f.name for f in self.fielddef.date()]

    @property
    def CHARS(self):
        return [f.name for f in self.fielddef.oftype("char")]

    @property
    def CONTACTS(self):
        return [f.name for f in self.fielddef.oftype("contact")]

    @property
    def PERSONNAMES(self):
        return [f.name for f in self.fielddef.oftype("personname")]

    @property
    def I18N(self):
        return [f.name for f in self.fielddef.i18n()]

    @property
    def LIMITED(self):
        return [f.name for f in self.fielddef.limited()]

    @property
    def CHOICES(self):
        return [f.name for f in self.fielddef.choices()]

    def open_xls(self, xlsfile):
        self.workbook = xlrd.open_workbook(xlsfile, formatting_info=True)
        try:
            self.sheet = self.workbook.sheet_by_index(0)
        except IOError:
            self.add_error(None, ERROR_CODES["bad_xls"], fatal=True)
        except IndexError:
            self.add_error(None, ERROR_CODES["worksheet_not_found"], fatal=True)

    def is_valid(self):
        return len(self.errors) > 0

    def coerce_int(self, val):
        """Liberally parse an integer value, assuming null -> 0"""
        try:
            return int(val)
        except ValueError:
            return

    def coerce_bool(self, val):
        """Parse a boolean value, assuming "yes", "true", "1" etc -> True."""
        if unicode(val).lower().strip() in ("yes", "true",):
            return True
        try:
            return int(val) == 1
        except ValueError:
            return False

    def print_errors(self):
        # sort by lin num
        errors = sorted(self.errors, key=lambda x: x[0])
        for error in errors:
            fullmsg = "%d: %s" % (error[0], error[1])
            if error[2]:
                LOG.warning(fullmsg)
            else:
                LOG.error(fullmsg)

    def add_error(self, row, msg, warn=False, fatal=False):
        fullmsg = "row %d: %s" % (row+1, msg)
        self.errors.append((row, msg, warn))
        if fatal or (self.raise_err and not warn):
            raise XLSError(fullmsg)

    def num_rows(self):
        if self.sheet is None:
            return -1
        return self.sheet.nrows - (self.HEADING_ROW + 1)

    def validate_headers(self):
        """Check header match watch we're expecting."""
        numheads = len(self.HEADINGS)
        heads = [h.value for h in self.sheet.row_slice(self.HEADING_ROW, 0, numheads)]
        diffs = set(heads).difference(self.HEADINGS)
        err = ERROR_CODES["unexpected_heading"]
        if diffs:
            for diff in diffs:
                self.add_error(self.HEADING_ROW, "%s: %s" % (err, diff))
            raise XLSError(err)        
        diffs = set(self.HEADINGS).difference(heads)
        if diffs:
            err = ERROR_CODES["missing_heading"]
            for diff in diffs:
                self.add_error(self.HEADING_ROW, "%s: %s" % (err, diff))
            raise XLSError(err)

    def validate(self, xlspath):
        """Check everything is A-Okay with the XLS data."""
        # These actions will stop any further validation
        # if they error
        self.open_xls(xlspath)
        try:
            self.validate_headers()
        except XLSError:
            return
        self.check_unique_columns()
        self.check_required_columns()
        for row in range(self.HEADING_ROW+1, self.sheet.nrows):
            data = [d.value for d in self.sheet.row_slice(row, 0, len(self.HEADINGS))]
            self.validate_row(row, OrderedDict(zip(self.HEADINGS, data)))

    def validate_row(self, rownum, rowdata):
        """Check a single row of data."""
        self.check_multiples(rownum, rowdata)
        self.check_limited(rownum, rowdata)
        self.check_person_names(rownum, rowdata)
        self.check_dates(rownum, rowdata)
        self.check_charfield_length(rownum, rowdata)
        self.check_choices(rownum, rowdata)

    def check_required_columns(self):
        """Make sure there are no blanks where there shouldn't
        be."""
        for colhead in self.REQUIRED:
            col = self.HEADINGS.index(colhead)
            rowsdata = [(i + self.HEADING_ROW, c.value) for i, c in \
                    enumerate(self.sheet.col_slice(
                        col, self.HEADING_ROW, self.sheet.nrows))]
            for i, data in rowsdata:
                if data is None or unicode(data).strip() == "":
                    self.add_error(i, "Missing value on required column: %s" % (
                        colhead))

    def check_unique_columns(self):
        """Check columns which should contain unique values
        actually do."""
        for colhead in self.UNIQUES:
            col = self.HEADINGS.index(colhead)
            rowsdata = [(i + self.HEADING_ROW, c.value) for i, c in \
                    enumerate(self.sheet.col_slice(
                        col, self.HEADING_ROW, self.sheet.nrows))]
            datarows = OrderedDict()
            for i, key in rowsdata:
                item = datarows.get(key)
                # don't count empty fields
                if key is None or key == "":
                    continue
                if item is None:
                    datarows[key] = [i]
                else:
                    datarows[key].append(i)
            for key, rows in datarows.iteritems():
                if len(rows) > 1:
                    header = self.sheet.cell(self.HEADING_ROW, col).value
                    self.add_error(
                            rows[0], "Duplicate on unique column: %s: '%s' %s" % (
                                header, key, [r+1 for r in rows[1:]]))

    def check_charfield_length(self, rownum, rowdata):
        """Check char fields aren't longer than 255 chars."""
        for field in self.CHARS:
            # just pretend everything's a multi-value
            for item in split_multiple(rowdata.get(field, "")):
                if len(item) > MAX_CHARFIELD_LENGTH:
                    self.add_error(rownum, "Field over 255 characters: '%s'" % field)

    def check_multiples(self, rownum, rowdata):
        """Check fields that only allow single entries don't
        contain multiple ones."""
        for i, (key, val) in enumerate(rowdata.iteritems()):
            if len(split_multiple(unicode(val))) > 1 and key not in self.MULTIPLES:
                self.add_error(rownum, 
                        "Double-comma separator in a strictly single-value field: '%s'" % key)

    def check_limited(self, rownum, rowdata):
        """Check multiple entries with a limit don't exceed
        that limit."""
        for field in self.MULTIPLES:
            if field in self.LIMITED:
                fmax = self.fielddef.fields[field].limit
                if len(split_multiple(rowdata[field])) > fmax:
                    self.add_error(rownum,
                            "Multiple-value field exceeds value limit: '%s' (limit %d)" % (
                                field, fmax))

    def check_person_names(self, rownum, rowdata):
        for field in self.PERSONNAMES:
            for item in split_multiple(rowdata.get(field, "")):
                if item.startswith("[org] "):
                    continue
                if item.count(",") < 1:
                    self.add_error(rownum, "No 'comma' delimiting surname/given name in person name field '%s': '%s'" %
                            (field, item))
                elif item.count(",") > 1:
                    self.add_error(rownum, "Multiple 'commas' in name field '%s': '%s'" % (field, item))

    def check_choices(self, rownum, rowdata):
        """Check fields that must contain choices are limited to
        the appropriate values."""
        for fieldobj in self.fielddef.choices():
            name = fieldobj.name
            choices = fieldobj.choices
            if rowdata[name] not in choices:
                self.add_error(rownum,
                        "Invalid value for field '%s': '%s'. Must be one of: %s" % (
                            name, rowdata[name], ", ".join(["'%s'" % s for s in choices])))


    def check_dates(self, rownum, rowdata):
        """Check dates are in YYYY-MM-DD format.  A preceding 'c' for
        'circa' is allowed to indicate inexactness."""
        for field in self.DATES:
            for datestr in split_multiple(rowdata[field]):
                if datestr.startswith("c"):
                    datestr = datestr[1:]
                # hack! to rid int dates of coerced float points
                if datestr.endswith(".0"):
                    datestr = datestr[:-2]
                try:
                    parser.parse(datestr, yearfirst=True)
                except ValueError:
                    self.add_error(rownum, "Bad date string in field: '%s': %s" % (
                            datestr, field))


class Repository(XLSValidator):
    """Validator for Repository import."""
    name = "Repositories"

    def __init__(self, *args, **kwargs):
        kwargs["definitions"] = kwargs.get("definitions", "repositories.yaml")
        super(Repository, self).__init__(*args, **kwargs)

    def check_countrycode(self, rownum, rowdata):
        """Check we can lookup the country code."""
        code = utils.get_code_from_country(rowdata["country"].strip())
        if code is None:
            self.add_error(rownum, "Unable to find 2-letter country code at row: '%s'" % (
                rowdata["country"],))

    def validate_row(self, rownum, rowdata):
        """Check a single row of data."""
        super(Repository, self).validate_row(rownum, rowdata)
        self.check_countrycode(rownum, rowdata)


class Collection(XLSValidator):
    """Validator for Collection import."""    
    name = "Collections"
    
    def __init__(self, *args, **kwargs):
        kwargs["definitions"] = kwargs.get("definitions", "collections.yaml")
        super(Collection, self).__init__(*args, **kwargs)

    def validate_row(self, rownum, rowdata):
        """Check a single row of data."""
        super(Collection, self).validate_row(rownum, rowdata)



VALIDATORS = [Repository, Collection]


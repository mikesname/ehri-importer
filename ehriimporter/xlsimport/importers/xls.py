"""Import XLS files into ICA Atom."""

import re
import datetime
from incf.countryutils import data as countrydata
import phpserialize
import unicodedata
from sqlaqubit import models, keys, create_engine, init_models
from sqlalchemy.engine.url import URL
from sqlalchemy import and_

from xlsimport.validators import xls
from xlsimport import utils
from ordereddict import OrderedDict

class XLSImportError(Exception):
    """Excel import errors."""


SLUGIFY_STRIP_RE = re.compile(r'[^\w\s-]')
SLUGIFY_HYPHENATE_RE = re.compile(r'[-\s]+')
def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.

    From Django's "django/template/defaultfilters.py".
    """
    if not isinstance(value, unicode):
        value = unicode(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
    value = unicode(SLUGIFY_STRIP_RE.sub('', value).strip().lower())
    return SLUGIFY_HYPHENATE_RE.sub('-', value)


REPO_I18N = [
        u'authorized_form_of_name',
        u'history',
        u'geocultural_context',
        u'collecting_policies',
        u'holdings',
        u'finding_aids',
        u'research_services',
        u'desc_institution_identifier',
        u'institution_responsible_identifier',
        u'rules',
        u'status',
]

CONTACT_I18N = [
        u'contact_type',
        u'city',
        u'region',
]

class XLSRepositoryImporter(xls.XLSRepositoryValidator):
    """Import repository information."""

    def __init__(self, database, username, password, hostname="localhost", port=None, atomuser=None,
                rowfunc=None, donefunc=None):
        """Initialise database connection and session."""
        super(XLSRepositoryImporter, self).__init__()
        engine = create_engine(URL("mysql",
            username=username,
            password=password,
            host=hostname,
            database=database,
            port=port,
            query=dict(
                charset="utf8", 
                use_unicode=0
            )
        ))
        init_models(engine)
        self.session = models.Session()
        self.atomuser = atomuser
        self.donefunc = donefunc
        self.rowfunc = rowfunc
        self.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") 

    def validate_xls(self, xlsfile):
        """Check file is A-Okay."""
        self.validate(xlsfile)
        if self.errors:
            raise XLSImportError("XLS validation error: %s" % self.errors)

    def do(self, xlsfile):
        """Import an XLS file."""
        try:
            self.validate_xls(xlsfile)
            self.import_xls(xlsfile)
        finally:
            self.session.close()

    def import_xls(self, xlsfile):
        """Actually import the file."""

        self.user = self.session.query(models.User).filter(
                models.User.username == self.atomuser).one()
        self.parent = self.session.query(models.Actor)\
                .filter(models.Actor.id==keys.ActorKeys.ROOT_ID).one()
        # load default status and detail... this is where
        # SQLAlchemy gets horrible
        self.status = self.session.query(models.Term)\
                .filter(models.Term.taxonomy_id == keys.TaxonomyKeys\
                    .DESCRIPTION_STATUS_ID)\
                .join(models.TermI18N, models.Term.id == models.TermI18N.id)\
                .filter(models.TermI18N.name == "Draft").one()
        self.detail = self.session.query(models.Term)\
                .filter(models.Term.taxonomy_id == keys.TaxonomyKeys\
                    .DESCRIPTION_DETAIL_LEVEL_ID)\
                .join(models.TermI18N, models.Term.id == models.TermI18N.id)\
                .filter(models.TermI18N.name == "Partial").one()

        # running count of slugs used so far in the import transaction
        self.slugs = {}


        for row in range(self.HEADING_ROW+1, self.sheet.nrows):
            data = [d.value for d in self.sheet.row_slice(row, 0, len(self.HEADINGS))]
            self.import_row(row, OrderedDict(zip(self.HEADINGS, data)))

        self.session.commit()
        if self.donefunc:
            self.donefunc()


    def import_row(self, rownum, rowdata, lang="en"):
        """Import a single repository."""
        code = utils.get_code_from_country(rowdata["country"].strip())
        name = rowdata["authorized_form_of_name"]
        # FIXME: wrong lang, etc
        repo = models.Repository(
            identifier="repo%06d%s" % (rownum, code),
            entity_type_id=keys.TermKeys.CORPORATE_BODY_ID,
            source_culture=lang,
            parent=self.parent,
            description_status=self.status,
            description_detail=self.detail,
            desc_status=self.status,
            desc_detail=self.detail
        )
        self.session.add(repo)
        revision = "Imported from EHRI spreadsheet at: %s" % self.timestamp
        i18ndict = dict((k, v) for k, v in rowdata.iteritems() \
                if k in REPO_I18N)
        i18ndict.update(desc_revision_history=revision, desc_rules="ISDIAH",
                desc_sources="\n".join(rowdata["sources"].split(",,")))
        repo.set_i18n(i18ndict, lang)

        repo.slug.append(models.Slug(
            slug=self.unique_slug(models.Slug, name) 
        ))

        if rowdata["notes"].strip():
            comment = models.Note(
                    object_id=repo.id,
                    type_id=keys.TermKeys.MAINTENANCE_NOTE_ID,
                    user=self.user,
                    source_culture=lang,
                    scope="QubitRepository"
            )
            repo.notes.append(comment)
            comment.set_i18n(dict(
                    content=rowdata["notes"],
            ), lang)

        namedict = dict(
                parallel_forms_of_name=keys.TermKeys.PARALLEL_FORM_OF_NAME_ID,
                other_names=keys.TermKeys.OTHER_FORM_OF_NAME_ID
        )
        for field, termid in namedict.iteritems():
            for name in [on for on in rowdata[field].split(",,") \
                        if on.strip() != ""]:
                othername = models.OtherName(
                        type_id=termid,
                        source_culture=lang
                )
                repo.other_names.append(othername)
                othername.set_i18n(dict(
                    name=name
                ), lang)

        def cleanfloat(f):
            if isinstance(f, float):
                return unicode(int(f))
            return f

        contact = models.ContactInformation(
            source_culture=lang,
            primary_contact=True,
            contact_person=rowdata["contact_person"],
            country_code=code,
            email=rowdata["email"].split(",,")[0],
            website=rowdata["website"].split(",,")[0],
            postal_code=cleanfloat(rowdata["postal_code"]).split(",,")[0],
            street_address=rowdata["street_address"],
            fax=cleanfloat(rowdata["fax"]).split(",,")[0],
            telephone=cleanfloat(rowdata["telephone"]).split(",,")[0]
        )
        repo.contacts.append(contact)
        contact.set_i18n(dict(
                contact_type=rowdata["contact_type"],
                city=rowdata["city"],
                region=rowdata["region"],
                note="Import from EHRI contact spreadsheet"
        ), lang)

        langprop = models.Property(name="language", source_culture=lang)
        repo.properties.append(langprop)
        langprop.set_i18n(dict(value=phpserialize.dumps([lang])), lang)
        scriptprop = models.Property(name="script", source_culture=lang)
        repo.properties.append(scriptprop)
        scriptprop.set_i18n(dict(value=phpserialize.dumps(["Latn"])), lang)

        if self.rowfunc:
            self.rowfunc(repo)


    def unique_slug(self, model, value):
        """Get a slug not currently used in the DB."""
        suffix = 0
        potential = base = slugify(value)
        while True:
            if suffix:
                potential = "-".join([base, str(suffix)])
            if not self.session.query(model).filter(model.slug == potential).count()\
                    and self.slugs.get(potential) is None:
                self.slugs[potential] = True
                return potential
            # we hit a conflicting slug, so bump the suffix & try again
            suffix += 1




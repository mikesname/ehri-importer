"""Import XLS files into ICA Atom."""

import re
import datetime
from dateutil import parser
from incf.countryutils import data as countrydata
import phpserialize
import unicodedata
from sqlaqubit import models, keys, create_engine, init_models
from sqlalchemy.engine.url import URL
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import and_

from xlsimport import validators
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


class XLSImportError(Exception):
    """Something went wrong with the import."""


class XLSImporter(object):
    """Base class for repository importer."""
    def __init__(self, database=None, username=None, 
                password=None, hostname="localhost", port=None, atomuser=None,
                rowfunc=None, donefunc=None): 
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
        self.donefunc = donefunc
        self.rowfunc = rowfunc
        self.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        self.user = self.session.query(models.User).filter(
                models.User.username == atomuser).one()
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
        self.ids = {}

    def random_slug(self):
        """Get a completely random 6-letter slug (for things
        like Event objects - don't blame me for this.)"""
        while True:
            potential = utils.get_random_string(6)
            if not self.session.query(models.Slug)\
                    .filter(models.Slug.slug == potential).count():
                return potential

    def unique_slug(self, value):
        """Get a slug not currently used in the DB. FIXME: This
        is not an atomic operation."""
        suffix = 0
        potential = base = slugify(value)
        while True:
            if suffix:
                potential = "-".join([base, str(suffix)])
            if not self.session.query(models.Slug)\
                    .filter(models.Slug.slug == potential).count()\
                        and self.slugs.get(potential) is None:
                self.slugs[potential] = True
                return potential
            # we hit a conflicting slug, so bump the suffix & try again
            suffix += 1

    def unique_identifier(self, model, prefix, suffix, format="%d"):
        """Get an id based on an incremented index of the
        object count for the given model.  FIXME: Not very safe 
        or atomic."""
        id = self.session.query(models.Object)\
                .order_by("id DESC").limit(1).one().id
        return (u"%s" + format + "%s") % (prefix, id + 1, suffix)

    def import_xls(self, xlsfile):
        """Actually import the file."""
        for row in range(self.HEADING_ROW+1, self.sheet.nrows):
            data = [d.value for d in self.sheet.row_slice(row, 0, len(self.HEADINGS))]
            obj = self.import_row(row, OrderedDict(zip(self.HEADINGS, data)))
            if self.rowfunc:
                self.rowfunc(obj)

        self.session.commit()
        if self.donefunc:
            self.donefunc()

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

    def import_row(self, rownum, rowdata, lang="en"):
        """Abstract implementation."""
        pass

    def add_note(self, item, record, field, typekey, scope, lang="en"):
        """Add a note record with the given type id, i.e. 
        ARCHIVIST_NOTE_ID, MAINTENANCE_NOTE_ID."""
        text = record[field].strip()
        if text:
            note = models.Note(
                    object_id=item.id,
                    type_id=typekey,
                    user=self.user,
                    source_culture=lang,
                    scope=scope
            )
            item.notes.append(note)
            note.set_i18n(dict(content=text), lang)

    def add_alt_names(self, item, record, field, termid, lang="en"):
        """Add an alternative name with the given term id, i.e.
        OTHER_FORM_OF_NAME_ID, PARALLEL_FORM_OF_NAME_ID."""
        for name in [on for on in record[field].split(",,") \
                    if on.strip() != ""]:
            othername = models.OtherName(
                    object_id=item.id,
                    type_id=termid,
                    source_culture=lang
            )
            item.other_names.append(othername)
            othername.set_i18n(dict(
                name=name
            ), lang)

    def add_date(self, datestr, item, typeid, lang="en"):
        """Add a date as an event object."""
        if datestr.startswith("c"):
            datestr = datestr[1:]
        # rely on the validator to check this doesn't explode
        date = parser.parse(datestr, yearfirst=True)
        event = models.Event(start_date=str(date), end_date=str(date),
                type_id=typeid,
                information_object_id=item.id,
                source_culture=lang)
        item.events.append(event)
        # add a random slug for the event (this is really wrong
        # but it's how qubit works...
        event.slug.append(models.Slug(slug=self.random_slug()))            

    def add_property(self, item, name, value, lang="en"):
        """Add a property to the object."""
        prop = models.Property(name=name, source_culture=lang)
        item.properties.append(prop)
        prop.set_i18n(dict(value=phpserialize.dumps(value)), lang)



class Repository(validators.Repository, XLSImporter):
    """Import repository information."""
    def __init__(self, *args, **kwargs):    
        XLSImporter.__init__(self, *args, **kwargs)
        validators.Repository.__init__(self)
        self.parent = self.session.query(models.Actor)\
                .filter(models.Actor.id==keys.ActorKeys.ROOT_ID).one()

    def import_row(self, rownum, record, lang="en"):
        """Import a single repository."""
        code = utils.get_code_from_country(record["country"].strip())
        name = record["authorized_form_of_name"]
        # FIXME: wrong lang, etc
        print name
        identifier = self.unique_identifier(models.Repository,
                "r", code, format="%06d")
        repo = models.Repository(
            identifier=identifier,
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
        i18ndict = dict((k, v) for k, v in record.iteritems() \
                if k in self.I18N)
        i18ndict.update(desc_revision_history=revision, desc_rules="ISDIAH",
                desc_sources="\n".join(record["sources"].split(",,")))
        repo.set_i18n(i18ndict, lang)

        # add a slug
        repo.slug.append(models.Slug(slug=self.unique_slug(name)))

        # add a note
        self.add_note(repo, record, "notes", 
                keys.TermKeys.MAINTENANCE_NOTE_ID, 
                "QubitRepository", lang)

        # add other & parallel names, with the correct Term ID.
        altnamedict = dict(
                parallel_forms_of_name=keys.TermKeys.PARALLEL_FORM_OF_NAME_ID,
                other_forms_of_name=keys.TermKeys.OTHER_FORM_OF_NAME_ID
        )
        for name, key in altnamedict.iteritems():
            self.add_alt_names(repo, record, name, key, lang)

        # extract the address fields
        self.add_addresses(repo, record, code, lang)

        # add various properties...
        propdict = dict(language_of_description="languageOfDescription", 
                script_of_description="scriptOfDescription")
        for name, prop in propdict.iteritems():
            value = [v for v in record[name].split(",,") if v.strip() != ""]
            self.add_property(repo, prop, value, lang)

        # handle ehri-specific metadata
        ehrimeta = dict(
                ehriPriority=self.coerce_int(record["ehri_priority"]),
                ehriCopyrightIssue=self.coerce_bool(record["ehri_copyright"])
        )
        self.add_property(repo, "ehrimeta", ehrimeta, lang)
        return repo

    def add_addresses(self, repo, record, countrycode, lang):
        """Add addresses.  These are all multiple fields because
        institutions could potentially have more than one address,
        although in practise it's likely to be just email/phone that
        we have more than one of.  Cue ugly hacks."""
        # oh god this makes me want to cry... 
        def cleanfloat(f):
            if isinstance(f, float):
                return unicode(int(f))
            return f

        # we must have a primary contact containing the country code
        # which is mandatory
        pcontact = models.ContactInformation(primary_contact=True,
                country_code=countrycode, source_culture=lang)
        repo.contacts.append(pcontact)
        pcontact.set_i18n(dict(
                    contact_type=record["contact_type"],
                    city=record["city"],
                    region=record["region"],
                    note="Import from EHRI contact spreadsheet"
            ), lang) 

        # some fields can have multiple values, which we need
        # to stick in a secondary contact model
        contact_fields = list(set(self.CONTACTS).difference(self.I18N))
        contacts = []
        for field in contact_fields:
            multival = record.get(field, "")
            fieldvals = [c for c in cleanfloat(multival).split(",,") if c != ""]
            for i in range(len(fieldvals)):                
                if i + 1 > len(contacts):
                    contacts.append({})
                contacts[i][field] = fieldvals[i]

        if contacts:
            for key, value in contacts[0].iteritems():
                setattr(pcontact, key, value)
            for contact in contacts[1:]:
                seccontact = models.ContactInformation(**contact)
                seccontact.source_culture = lang
                repo.contacts.append(seccontact)


class Collection(validators.Collection, XLSImporter):
    """Import repository information."""
    def __init__(self, *args, **kwargs):    
        XLSImporter.__init__(self, *args, **kwargs)
        validators.Collection.__init__(self)

        self.parent = self.session.query(models.InformationObject)\
                .filter(models.InformationObject.id==keys.InformationObjectKeys.ROOT_ID)\
                .one()
        self.pubtype = self.session.query(models.Term)\
                .filter(models.Term.taxonomy_id == keys.TaxonomyKeys\
                    .STATUS_TYPE_ID)\
                .join(models.TermI18N, models.Term.id == models.TermI18N.id)\
                .filter(models.TermI18N.name == "publication").one()
        self.lod_coll = self.session.query(models.Term)\
                .filter(models.Term.taxonomy_id == keys.TaxonomyKeys\
                    .LEVEL_OF_DESCRIPTION_ID)\
                .join(models.TermI18N, models.Term.id == models.TermI18N.id)\
                .filter(models.TermI18N.name == "Collection").one()
        self.pubstatus = self.session.query(models.Term)\
                .filter(models.Term.taxonomy_id == keys.TaxonomyKeys\
                    .PUBLICATION_STATUS_ID)\
                .join(models.TermI18N, models.Term.id == models.TermI18N.id)\
                .filter(models.TermI18N.name == "draft").one()

    def import_row(self, rownum, record, lang="en"):
        """Import a single collection."""
        repoid = record["repository_code"]

        # get the repo and let it error if not found
        try:
            repo = self.session.query(models.Repository)\
                    .filter(models.Repository.identifier==repoid)\
                    .one()
        except NoResultFound:
            raise XLSImportError("Unable to find repository with identifier: %s" % (
                repoid))

        identifier = self.unique_identifier(models.InformationObject,
                "c", repo.contacts[0].country_code)
        info = models.InformationObject(
            identifier=identifier,
            source_culture=lang,
            parent=self.parent,
            repository_id=repo.id,
            level_of_description=self.lod_coll,
            description_status_id=self.status.id,
            description_detail_id=self.detail.id,
            source_standard="ISAD(G) 2nd Edition"
        )
        self.session.add(info)
        revision = "Imported from EHRI Spreadsheet at: %s" % self.timestamp
        i18ndict = dict((k, v) for k, v in record.iteritems() \
                if k in self.I18N)
        i18ndict.update(desc_revision_history=revision, desc_rules="ISAD(G)",
                desc_sources="\n".join(record["sources"].split(",,")))
        info.set_i18n(i18ndict, lang)

        # add a slug
        info.slug.append(models.Slug(slug=self.unique_slug(record["title"])))

        # add various types of note...
        notedict = dict(
                notes=keys.TermKeys.MAINTENANCE_NOTE_ID,
                archivist_note=keys.TermKeys.ARCHIVIST_NOTE_ID,
                publication_note=keys.TermKeys.PUBLICATION_NOTE_ID
        )
        for name, key in notedict.iteritems():
            self.add_note(info, record, name, key, "InformationObject", lang)

        self.add_alt_names(info, record, "other_forms_of_title", 
                keys.TermKeys.OTHER_FORM_OF_NAME_ID, lang)

        # TODO: Work out a way on encoding date ranges in Excel
        for field in self.DATES:
            for datestr in [ds for ds in record[field].split(",,") if ds.strip() != ""]:
                self.add_date(datestr, info, keys.TermKeys.CREATION_ID, lang)

        # add a publication status ID
        status = models.Status(object=info, 
                type_id=self.pubtype.id, status_id=self.pubstatus.id)
        self.session.add(status)

        propdict = dict(
                language="language",
                script="script",
                language_of_description="languageOfDescription",
                script_of_description="scriptOfDescription"
        )
        for name, prop in propdict.iteritems():
            values = [v for v in record[name].split(",,") if v.strip() != ""] 
            self.add_property(info, prop, values, lang)

        # handle ehri-specific metadata
        ehrimeta = dict(
                ehriPriority=self.coerce_int(record["ehri_priority"]),
                ehriCopyrightIssue=self.coerce_bool(record["ehri_copyright"]),
                ehriScope=self.coerce_int(record["ehri_scope"])
        )
        self.add_property(info, "ehrimeta", ehrimeta, lang)
        return info


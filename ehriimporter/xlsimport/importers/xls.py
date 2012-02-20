"""Import XLS files into ICA Atom."""

import re
import datetime
from incf.countryutils import data as countrydata
import phpserialize
import unicodedata
from sqlaqubit import models, keys, create_engine, init_models
from sqlalchemy.engine.url import URL
from sqlalchemy.orm.exc import NoResultFound
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


CONTACT_I18N = [
        u'contact_type',
        u'city',
        u'region',
]


class XLSImportError(Exception):
    """Something went wrong with the import."""


class XLSImporter(object):
    """Base class for repository importer."""
    def __init__(self, database, username, password, hostname="localhost", port=None, atomuser=None,
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

    def unique_slug(self, model, value):
        """Get a slug not currently used in the DB. FIXME: This
        is not an atomic operation."""
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

    def unique_identifier(self, model, prefix, suffix):
        """Get an id based on an incremented index of the
        object count for the given model.  FIXME: Not very safe 
        or atomic."""
        id = self.session.query(models.Object)\
                .order_by("id DESC").limit(1).one().id
        return u"%s%d%s" % (prefix, id + 1, suffix)

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

    def add_property(self, item, record, recordname, propname, lang="en"):
        """Add a property to the object."""
        items = record[recordname].split(",,")        
        prop = models.Property(name=propname, source_culture=lang)
        item.properties.append(prop)
        prop.set_i18n(dict(value=phpserialize.dumps(items)), lang)



class XLSRepositoryImporter(xls.XLSRepositoryValidator, XLSImporter):
    """Import repository information."""
    def __init__(self, *args, **kwargs):    
        XLSImporter.__init__(self, *args, **kwargs)
        xls.XLSRepositoryValidator.__init__(self)
        self.parent = self.session.query(models.Actor)\
                .filter(models.Actor.id==keys.ActorKeys.ROOT_ID).one()

    def import_row(self, rownum, record, lang="en"):
        """Import a single repository."""
        code = utils.get_code_from_country(record["country"].strip())
        name = record["authorized_form_of_name"]
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
        i18ndict = dict((k, v) for k, v in record.iteritems() \
                if k in self.I18N)
        i18ndict.update(desc_revision_history=revision, desc_rules="ISDIAH",
                desc_sources="\n".join(record["sources"].split(",,")))
        repo.set_i18n(i18ndict, lang)

        # add a slug
        repo.slug.append(models.Slug(
            slug=self.unique_slug(models.Slug, name) 
        ))

        # add a note
        if record["notes"].strip():
            comment = models.Note(
                    object_id=repo.id,
                    type_id=keys.TermKeys.MAINTENANCE_NOTE_ID,
                    user=self.user,
                    source_culture=lang,
                    scope="QubitRepository"
            )
            repo.notes.append(comment)
            comment.set_i18n(dict(
                    content=record["notes"],
            ), lang)
        # add other & parallel names, with the correct Term ID.
        altnamedict = dict(
                parallel_forms_of_name=keys.TermKeys.PARALLEL_FORM_OF_NAME_ID,
                other_names=keys.TermKeys.OTHER_FORM_OF_NAME_ID
        )
        for field, termid in altnamedict.iteritems():
            for name in [on for on in record[field].split(",,") \
                        if on.strip() != ""]:
                othername = models.OtherName(
                        type_id=termid,
                        source_culture=lang
                )
                repo.other_names.append(othername)
                othername.set_i18n(dict(
                    name=name
                ), lang)

        self.add_addresses(repo, record, code, lang)

        propdict = dict(language="language", script="script")
        for name, prop in propdict.iteritems():
            self.add_property(repo, record, name, prop, lang)
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

        contact_fields = ["contact_person", "street_address", "postal_code",
                "email", "telephone", "fax", "website"]
        contact_i18n = ["contact_type", "city", "region"]
        contacts = []
        for field in contact_fields:
            multival = record.get(field, "")
            fieldvals = [c for c in cleanfloat(multival).split(",,") if c != ""]
            for i in range(len(fieldvals)):                
                if i + 1 > len(contacts):
                    contacts.append({})
                contacts[i][field] = fieldvals[i]

        for i in range(len(contacts)):
            contact = contacts[i]
            contact.update(source_culture=lang,
                    primary_contact=i==0,
                    country_code=countrycode)
            addcontact = models.ContactInformation(**contact)
            repo.contacts.append(addcontact)
            # only set i18n record for the first contact
            if i > 0:
                break
            addcontact.set_i18n(dict(
                    contact_type=record["contact_type"],
                    city=record["city"],
                    region=record["region"],
                    note="Import from EHRI contact spreadsheet"
            ), lang)


class XLSCollectionImporter(xls.XLSCollectionValidator, XLSImporter):
    """Import repository information."""
    def __init__(self, *args, **kwargs):    
        XLSImporter.__init__(self, *args, **kwargs)
        xls.XLSCollectionValidator.__init__(self)

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
                .filter(models.TermI18N.name == "published").one()

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
                "coll", repo.contacts[0].country_code)
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
        revision = "%s: Imported from AIM25" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        i18ndict = dict((k, v) for k, v in record.iteritems() \
                if k in self.I18N)
        i18ndict.update(desc_revision_history=revision, desc_rules="ISAD(G)",
                desc_sources="\n".join(record["sources"].split(",,")))
        info.set_i18n(i18ndict, lang)

        info.slug.append(models.Slug(
            slug=self.unique_slug(models.Slug, record["title"]) 
        ))

        # add various types of note...
        notedict = dict(
                notes=keys.TermKeys.MAINTENANCE_NOTE_ID,
                archivist_note=keys.TermKeys.ARCHIVIST_NOTE_ID,
                publication_note=keys.TermKeys.PUBLICATION_NOTE_ID
        )
        for notename, typekey in notedict.iteritems():
            if record[notename]:
                print "Adding %s: %s" % (notename, record[notename])
                note = models.Note(
                        object_id=info.id,
                        type_id=typekey,
                        user=self.user,
                        source_culture=lang,
                        scope="InformationObject"
                )
                info.notes.append(note)
                note.set_i18n(dict(
                        content=record[notename],
                ), lang)

        #event = self.parse_date(record["dates"], info, lang)
        #if event:
        #    info.events.append(event)

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
            self.add_property(info, record, name, prop, lang)
        return info


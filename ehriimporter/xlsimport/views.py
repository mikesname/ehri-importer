"""XLS Import/validate views."""

import os
import tempfile

from django.shortcuts import render

from xlsimport import forms, tasks
from validators import xls
from importers import xls as xlsi



def save_to_temp(f):
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        for chunk in f.chunks():
            temp.write(chunk)
        temp.close()
    return temp.name


def validate(request):
    """Validate an XLS."""
    template = "xlsimport/validate.html"
    form = forms.XLSForm()
    context = dict()
    if request.method == "POST":
        form = forms.XLSForm(request.POST, request.FILES)
        if form.is_valid():
            name = request.FILES["xlsfile"].name
            temppath = save_to_temp(request.FILES["xlsfile"])
            validator = getattr(xls, form.cleaned_data["xlstype"])()
            validator.validate(temppath)
            os.unlink(temppath)
            context.update(errors=validator.errors, validator=validator)
    context.update(form=form)
    return render(request, template, context)


def importxls(request):
    """Import an XLS."""
    template = "xlsimport/import.html"
    form = forms.XLSImportForm()
    context = dict()
    if request.method == "POST":
        form = forms.XLSImportForm(request.POST, request.FILES)
        if form.is_valid():
            name = request.FILES["xlsfile"].name
            temppath = save_to_temp(request.FILES["xlsfile"])
            result = tasks.import_xls.delay(temppath, "mike")
            print "RESULT: %s" % result
            context.update(result=result)
    context.update(form=form)
    return render(request, template, context)



def help(request):
    """Show help about import spreadsheet format."""
    importers = xls.VALIDATORS
    template = "xlsimport/help.html"
    context = dict(importers=importers)
    return render(request, template, context)


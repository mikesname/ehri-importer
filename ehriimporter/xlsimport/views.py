"""XLS Import/validate views."""

import os
import tempfile

from django.shortcuts import render

from xlsimport import forms

from sqlaqubit.validators import xls


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
    context = dict(form=form)
    if request.method == "POST":
        form = forms.XLSForm(request.POST, request.FILES)
        if form.is_valid():
            name = request.FILES["xlsfile"].name
            temppath = save_to_temp(request.FILES["xlsfile"])
            validator = getattr(xls, form.cleaned_data["xlstype"])()
            validator.validate(temppath)
            os.unlink(temppath)
            context.update(errors=validator.errors, validator=validator)
    return render(request, template, context)


def help(request):
    """Show help about import spreadsheet format."""
    importers = [getattr(xls, attr) for attr in dir(xls) \
            if hasattr(getattr(xls, attr), "name")]
    template = "xlsimport/help.html"
    context = dict(importers=importers)
    return render(request, template, context)


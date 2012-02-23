"""XLS Import/validate views."""

import os
import tempfile

from django.shortcuts import render, redirect

from celery import result

from xlsimport import forms, tasks
from validators import xls
from importers import xls as xlsi



def save_to_temp(f):
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        for chunk in f.chunks():
            temp.write(chunk)
        temp.close()
    return temp.name


def home(request):
    template = "xlsimport/home.html"
    context = {}
    return render(request, template, context)


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
    context = dict(form=form)
    if request.method == "POST":
        form = forms.XLSImportForm(request.POST, request.FILES)
        if form.is_valid():
            name = request.FILES["xlsfile"].name
            temppath = save_to_temp(request.FILES["xlsfile"])
            validator = getattr(xls, form.cleaned_data["xlstype"])()
            validator.validate(temppath)
            # bail out if we get an error
            if validator.errors:
                context.update(errors=validator.errors, validator=validator)
                os.unlink(temppath)
                return render(request, template, context)
            async = tasks.ImportXLSTask.delay(validator.__class__.__name__, temppath)
            return redirect("xls_progress", task_id=async.task_id)
    context.update(form=form)
    return render(request, template, context)


def progress(request, task_id):
    """Show progress for a running import."""
    template = "xlsimport/progress.html" if not request.is_ajax() \
            else "xlsimport/_progress.html"
    async = result.AsyncResult(task_id)
    context = dict(async=async)
    progress = 0
    if async.status == "PROGRESS":
        info = async.info
        progress = round(float(info["current"]) / float(info["total"]) * 100)
    elif async.successful():
        progress = 100
    context.update(progress=progress)
    return render(request, template, context)


def help(request):
    """Show help about import spreadsheet format."""
    importers = xls.VALIDATORS
    template = "xlsimport/help.html"
    context = dict(importers=importers)
    return render(request, template, context)


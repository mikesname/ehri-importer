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
    if request.method == "POST":
        form = forms.XLSForm(request.POST, request.FILES)
        if not form.is_valid():
            context = dict(form=form)
            return render(request, template, context)
        name = request.FILES["xlsfile"].name
        temppath = save_to_temp(request.FILES["xlsfile"])
        validator = getattr(xls, form.cleaned_data["xlstype"])(temppath)
        try:
            validator.validate()
        except xls.XLSError:
            pass
        os.unlink(temppath)

        # form is good, so render the report template
        context = dict(form=form, errors=validator.errors,
                name=name, validator=validator)
        return render(request, template, context)



    form = forms.XLSForm()
    context = dict(form=form)
    return render(request, template, context)


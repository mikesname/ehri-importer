"""XLS Import form."""


from django import forms

XLSTYPES = (
        ("Repository", "Institutions"),
        ("Collection", "Collections"),
)

class XLSForm(forms.Form):
    """Form which allows uploading an XLS file."""
    xlsfile = forms.FileField(label="Excel file")
    xlstype = forms.ChoiceField(choices=XLSTYPES, label="Spreadsheet type")


class XLSImportForm(XLSForm):
    """Form for importing data."""

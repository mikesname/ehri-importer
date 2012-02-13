"""XLS Import form."""


from django import forms

XLSTYPES = (
        ("XLSRepositoryValidator", "Institutions"),
        ("XLSCollectionValidator", "Collections"),
)


class XLSForm(forms.Form):
    """Form which allows uploading an XLS file."""
    xlsfile = forms.FileField(label="Excel file")
    xlstype = forms.ChoiceField(choices=XLSTYPES, label="Spreadsheet type")

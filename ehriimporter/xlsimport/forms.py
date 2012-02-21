"""XLS Import form."""


from django import forms

XLSTYPES = (
        ("XLSRepositoryValidator", "Institutions"),
        ("XLSCollectionValidator", "Collections"),
)

XLSIMPORTTYPES = (
        ("XLSRepositoryImporter", "Institutions"),
        ("XLSCollectionImporter", "Collections"),
)


class XLSForm(forms.Form):
    """Form which allows uploading an XLS file."""
    xlsfile = forms.FileField(label="Excel file")
    xlstype = forms.ChoiceField(choices=XLSTYPES, label="Spreadsheet type")


class XLSImportForm(XLSForm):
    """Form for importing data."""
    xlstype = forms.ChoiceField(choices=XLSIMPORTTYPES, 
            label="Spreadsheet type")

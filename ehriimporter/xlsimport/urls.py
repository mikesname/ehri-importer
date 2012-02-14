"""XLS Import URLs."""

from django.conf.urls.defaults import *

from xlsimport import forms, views


urlpatterns = patterns('',
    url(r'^validate/?$', views.validate, name='xls_validate'),
    url(r'^help/?$', views.help, name='xls_help'),
)


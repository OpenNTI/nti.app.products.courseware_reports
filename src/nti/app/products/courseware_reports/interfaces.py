#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import interface

from zope.viewlet.interfaces import IViewletManager

from zope.security.permission import Permission

from nti.contenttypes.reports.interfaces import IReport

from nti.schema.field import TextLine

# Until we have true pluggable auth-folders that we traverse through
# we might add instructors to a role having this permission using
# traversal events
ACT_VIEW_REPORTS = Permission('nti.actions.courseware_reports.view_reports')


class IPDFReportView(interface.Interface):
    """
    An interface that all the reporting views
    that generate PDFs and work from the same set
    of PDF templates are expected to implement.

    In this way, we have a distinct way of registering :mod:`z3c.macro``
    definitions.
    """

    filename = TextLine(title=u"The final portion of the file name, usually the view name",
                        required=False,
                        default=u"")

    report_title = TextLine(title=u"The title of the report.")


class IPDFReportHeaderManager(IViewletManager):
    """
    Viewlet manager for the headers of pdf reports.
    """


class IInstructorReport(IReport):
    """
    Interface defining a report to be viewed by an instructor
    """
    permission = TextLine(title=u"The permission level required to access this report",
                          required=False)

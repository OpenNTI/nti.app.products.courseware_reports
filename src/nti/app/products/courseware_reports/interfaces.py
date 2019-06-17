#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from zope.security.permission import Permission

from nti.contenttypes.reports.interfaces import IReport

from nti.dataserver.users.interfaces import IProfileDisplayableSupplementalFields

from nti.schema.field import Choice

# Until we have true pluggable auth-folders that we traverse through
# we might add instructors to a role having this permission using
# traversal events
ACT_VIEW_REPORTS = Permission('nti.actions.courseware_reports.view_reports')


class IInstructorReport(IReport):
    """
    Interface defining a report to be viewed by an instructor
    """
    permission = Choice(vocabulary='Permission Ids',
                        title=u"The permission level required to access this report",
                        required=False)


class IRosterReportSupplementalFields(IProfileDisplayableSupplementalFields):
    """
    A IProfileDisplayableSupplementalFields utility that can add additional
    (profile) fields to roster CSV reports.
    """

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from zope.security.zcml import Permission

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.app.products.courseware_reports.reports import InstructorReport

from nti.contenttypes.reports.zcml import registerReport
from nti.contenttypes.reports.zcml import IRegisterReport

logger = __import__('logging').getLogger(__name__)


class IRegisterInstructorReport(IRegisterReport):
    """
    Interface representing a registration of a new instructor report, defining behavior
    of the various fields
    """

    permission = Permission(title=u"The permission level required to access this report",
                            required=False)


def registerInstructorReport(_context, name, title, description, contexts,
                             supported_types, registration_name=None):
    """
    Take the items from ZCML, turn it into a report object and register it as a
    new utility in the current context
    """
    registerReport(_context, name, title, description,
                   supported_types=supported_types,
                   permission=None,
                   contexts=contexts,
                   registration_name=registration_name,
                   report_class=InstructorReport,
                   report_interface=IInstructorReport)

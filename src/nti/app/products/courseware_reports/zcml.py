#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.app.products.courseware_reports.reports import InstructorReport

from nti.contenttypes.reports.zcml import registerReport
from nti.contenttypes.reports.zcml import IRegisterReport

from nti.schema.field import TextLine


class IRegisterInstructorReport(IRegisterReport):
    """
    Interface representing a registration of a new instructor report, defining behavior
    of the various fields
    """

    permission = TextLine(title=u"The permission level required to access this report",
                          required=False)

def registerInstructorReport(_context, name, title, description, contexts,
                             supported_types, link_provider=None, registration_name=None):
    """
    Take the items from ZCML, turn it into a report object and register it as a
    new utility in the current context
    """
    registerReport(_context, name, title, description,
                   permission=None,
                   contexts=contexts,
                   supported_types=supported_types,
                   link_provider=link_provider,
                   registration_name=registration_name,
                   report_class=InstructorReport,
                   report_interface=IInstructorReport)

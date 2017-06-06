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


class IRegisterInstructorReport(IRegisterReport):
    """
    Interface representing a registration of a new instructor report, defining behavior
    of the various fields
    """

def registerInstructorReport(_context, name, description, interface_context,
                             supported_types, permission=None, registration_name=None):
    """
    Take the items from ZCML, turn it into a report object and register it as a
    new utility in the current context
    """
    registerReport(_context, name, description,
                   permission=permission,
                   supported_types=supported_types,
                   interface_context=interface_context,
                   registration_name=registration_name,
                   report_class=InstructorReport,
                   report_interface=IInstructorReport)

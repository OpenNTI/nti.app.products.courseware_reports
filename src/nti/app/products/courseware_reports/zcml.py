#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import functools

from zope import interface
from zope import component

from zope.interface.interface import InterfaceClass

from zope.component.zcml import subscriber
from zope.component.zcml import utility

from zope.configuration.fields import Tokens
from zope.configuration.fields import GlobalObject

from nti.base._compat import text_

from nti.contenttypes.reports.interfaces import IReportContext
from nti.contenttypes.reports.interfaces import IReport

from nti.app.products.courseware_reports.reports import InstructorReport

from nti.contenttypes.reports.zcml import IRegisterReport
from nti.contenttypes.reports.zcml import registerReport

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.schema.field import TextLine

class IRegisterInstructorReport(IRegisterReport):
    """
    Interface representing a registration of a new instructor report, defining behavior
    of the various fields
    """
    permission = TextLine(title=u"The permission level required to access this report",
                          required=False)


def registerInstructorReport(_context, name, description, interface_context,
                             supported_types, registration_name=None):
    """
    Take the items from ZCML, turn it into a report object and register it as a
    new utility in the current context
    """

    if registration_name is None:
        registration_name = name

    supported_types = tuple(set(text_(s) for s in supported_types or ()))

    # Create the Report object to be used as a subscriber
    factory = functools.partial(InstructorReport,
                                name=text_(name),
                                description=text_(description),
                                interface_context=interface_context,
                                permission=None,
                                supported_types=supported_types)

    assert type(interface_context) is InterfaceClass, "Invalid interface"
    assert IReportContext in interface_context.__bases__, "Invalid report context interface"

    # Register the object as a subscriber
    subscriber(_context, provides=IInstructorReport,
               factory=factory, for_=(interface_context,))

    # Also register as utility to getch all
    utility(_context, provides=IReport,
            factory=factory, name=registration_name)

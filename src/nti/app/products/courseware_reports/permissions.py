#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import component
from zope import interface

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.contenttypes.reports.interfaces import IReportPredicate

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.contenttypes.courses.utils import get_course_instructors

from nti.dataserver.interfaces import IUser

from nti.app.products.courseware_reports.utils import find_course_for_user


@interface.implementer(IReportPredicate)
@component.adapter(IInstructorReport, IUser)
class InstructorReportPermission(object):
    """
    Evaluate if a user has permission to access
    a report within the context
    """
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, report, context, user):
        course = find_course_for_user(context, user)
        instructors = get_course_instructors(course)
        return user.username in instructors

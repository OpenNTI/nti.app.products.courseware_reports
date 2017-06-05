#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import component
from zope import interface

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.contenttypes.reports.interfaces import IReport
from nti.contenttypes.reports.interfaces import IReportPredicate

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.contenttypes.courses.utils import get_course_instructors

from nti.dataserver.interfaces import IUser

from nti.dataserver.authorization_acl import has_permission


@interface.implementer(IReportPredicate)
@component.adapter(IInstructorReport, IUser)
class InstructorReportPermission():

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, report, context, user):
        # Get the course. 
        course = self._get_course_instance(context)
        # Get the instructors for the course
        instructors = get_course_instructors(course)
        # Return if the user is in the instructorset
        return user.username in instructors

    def _get_course_instance(self, context):
        return ICourseInstance(context)

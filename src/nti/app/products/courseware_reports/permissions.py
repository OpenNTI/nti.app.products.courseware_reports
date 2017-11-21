#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from zope import component
from zope import interface

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.app.products.courseware_reports.utils import find_course_for_user

from nti.contenttypes.reports.interfaces import IReportPredicate

from nti.contenttypes.courses.utils import get_course_instructors

from nti.dataserver.authorization import is_admin_or_site_admin

from nti.dataserver.interfaces import IUser

logger = __import__('logging').getLogger(__name__)


@interface.implementer(IReportPredicate)
@component.adapter(IInstructorReport, IUser)
class InstructorReportPermission(object):
    """
    Evaluate if a user has permission to access a report within the context.
    Admins/SiteAdmins always have access, along with instructors.
    """
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, unused_report, context, user):
        if is_admin_or_site_admin(user):
            return True
        course = find_course_for_user(context, user)
        instructors = get_course_instructors(course)
        return user.username in instructors

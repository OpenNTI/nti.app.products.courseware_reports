#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from datetime import datetime

from pyramid.view import view_config

from nti.app.products.courseware_reports import MessageFactory as _
from nti.app.products.courseware_reports import VIEW_COURSE_ROSTER

from nti.app.products.courseware_reports.reports import _adjust_date
from nti.app.products.courseware_reports.reports import _format_datetime

from nti.app.products.courseware_reports.views.view_mixins import AbstractCourseReportView

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseEnrollments

from nti.dataserver.interfaces import IUser
from nti.dataserver.users.users import User
from nti.dataserver.users.interfaces import IFriendlyNamed

logger = __import__('logging').getLogger(__name__)


@view_config(context=ICourseInstance,
             name=VIEW_COURSE_ROSTER)
class CourseRosterReportPdf(AbstractCourseReportView):

    report_title = _(u'Course Roster Report')

    def __init__(self, context, request):
        self.context = context
        self.request = request

        if 'remoteUser' in request.params:
            self.remoteUser = request.params['remoteUser']
        else:
            self.remoteUser = self.getRemoteUser()

        self.options = {}

        if request.view_name:
            self.filename = request.view_name

    def __call__(self):
        self._check_access()
        options = self.options

        course = self.course

        enrollmentCourses = ICourseEnrollments(course)

        enrollments = []
        for record in enrollmentCourses.iter_enrollments():
            enrollRecord = {}

            user = IUser(record.Principal, None)

            if user is None:
                user = User.get_user(record.Principal)
            if user is None:
                # Deleted user
                continue

            user = IFriendlyNamed(user)
            
            enrollRecord["displayname"] = user.realname or user.alias or user.username
            enrollRecord["realname"] = user.realname
            enrollRecord["username"] = user.username
            enrollRecord["email"] = user.email

            if record.createdTime:
                time = datetime.fromtimestamp(record.createdTime)
                enrollRecord["enrollmentTime"] = _format_datetime(_adjust_date(time))
                enrollRecord["lastAccessed"] = ""

            enrollments.append(enrollRecord)

        options["enrollments"] = enrollments
        options["TotalEnrolledCount"] = enrollmentCourses.count_enrollments()
        return options

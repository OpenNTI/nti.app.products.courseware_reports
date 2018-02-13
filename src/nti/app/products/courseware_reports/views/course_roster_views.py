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

from zope import component

from zc.displayname.interfaces import IDisplayNameGenerator

from nti.analytics.stats.interfaces import IActivitySource

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

from nti.mailer.interfaces import IEmailAddressable

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

    def _name(self, user, friendly_named=None):
        displayname = component.getMultiAdapter((user, self.request), IDisplayNameGenerator)()

        if not friendly_named:
            friendly_named = IFriendlyNamed(user)

        if friendly_named.realname and displayname != friendly_named.realname:
            displayname = '%s (%s)' % (friendly_named.realname, displayname)
        return displayname

    def __call__(self):
        self._check_access()
        options = self.options

        course = self.course

        enrollmentCourses = ICourseEnrollments(course)

        enrollments = []
        for record in enrollmentCourses.iter_enrollments():
            enrollRecord = {}

            user = User.get_user(record.Principal)
            if user is None:
                # Deleted user
                continue

            enrollRecord["username"] = user.username

            fn_user = IFriendlyNamed(user)
            enrollRecord["displayname"] = self._name(user, friendly_named=fn_user)

            email_addressable = IEmailAddressable(user, None)
            enrollRecord["email"] = email_addressable.email if email_addressable else None

            enrollment_time = None
            if record.createdTime:
                time = datetime.fromtimestamp(record.createdTime)
                enrollment_time = _adjust_date(time)
                enrollRecord["enrollmentTime"] = _format_datetime(enrollment_time)

            accessed_time = enrollment_time
            activity_source = component.queryMultiAdapter((user, course), IActivitySource)
            if activity_source:
                latest = activity_source.activity(limit=1, order_by='timestamp')
                accessed_time = latest[0].timestamp if latest else None

            enrollRecord["lastAccessed"] = _format_datetime(accessed_time) if accessed_time else None

            enrollments.append(enrollRecord)

        options["enrollments"] = enrollments
        options["TotalEnrolledCount"] = enrollmentCourses.count_enrollments()
        return options

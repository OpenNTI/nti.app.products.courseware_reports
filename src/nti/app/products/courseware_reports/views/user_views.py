#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from pyramid.view import view_config

from zope import component

from pyramid.httpexceptions import HTTPForbidden

from datetime import datetime

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import ISiteAdminUtility

from nti.analytics.stats.interfaces import IActivitySource

from nti.app.products.courseware_reports import MessageFactory as _
from nti.app.products.courseware_reports import VIEW_USER_ENROLLMENT

from nti.app.products.courseware_reports.reports import _adjust_date
from nti.app.products.courseware_reports.reports import _format_datetime

from nti.app.products.courseware_reports.views.view_mixins import AbstractReportView

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.contenttypes.courses.utils import get_context_enrollment_records

from nti.dataserver.authorization import is_admin
from nti.dataserver.authorization import is_site_admin

logger = __import__('logging').getLogger(__name__)


@view_config(context=IUser,
             name=VIEW_USER_ENROLLMENT)
class UserEnrollmentReportPdf(AbstractReportView):
    report_title = _(u'User Enrollment Report')

    def _check_access(self):
        if is_admin(self.remoteUser) or self.context == self.remoteUser:
            return True

        if is_site_admin(self.remoteUser):
            admin_utility = component.getUtility(ISiteAdminUtility)
            if admin_utility.can_administer_user(self.remoteUser, self.context):
                return True

        raise HTTPForbidden()

    def get_user_info(self):
        return self.build_user_info(self.context)

    def generate_footer(self):
        date = _adjust_date(datetime.utcnow())
        date = date.strftime('%b %d, %Y %I:%M %p')
        title = self.report_title
        user = self.context.username
        return u"%s %s %s" % (title, user, date)

    def get_context_enrollment_records(self):
        return get_context_enrollment_records(self.context, self.remoteUser)

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
        records = self.get_context_enrollment_records()
        records = sorted(records, key=lambda x:x.createdTime)

        options["user"] = self.get_user_info()

        enrollments = []
        for record in records:
            enrollment = {}
            course = ICourseInstance(record)
            catalog_entry = ICourseCatalogEntry(course)
            enrollment["title"] = catalog_entry.title

            enrollment_time = None
            if record.createdTime:
                time = datetime.fromtimestamp(record.createdTime)
                enrollment_time = _adjust_date(time)
                enrollment["enrollmentTime"] = _format_datetime(enrollment_time)

            accessed_time = enrollment_time
            activity_source = component.queryMultiAdapter((self.context, course), IActivitySource)
            if activity_source:
                latest = activity_source.activity(limit=1, order_by='timestamp')
                accessed_time = latest[0].timestamp if latest else None

            enrollment["lastAccessed"] = _format_datetime(accessed_time) if accessed_time else None
            enrollments.append(enrollment)
        options['enrollments'] = enrollments

        return options

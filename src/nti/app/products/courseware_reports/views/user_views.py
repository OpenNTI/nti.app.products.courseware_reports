#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import csv
import six

from datetime import datetime

from io import BytesIO

from pyramid.config import not_

from pyramid.httpexceptions import HTTPForbidden

from pyramid.view import view_config

from zope import component

from nti.coremetadata.interfaces import ILastSeenProvider

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import ISiteAdminUtility

from nti.app.products.courseware_reports import MessageFactory as _
from nti.app.products.courseware_reports import VIEW_USER_ENROLLMENT

from nti.app.products.courseware_reports.views.view_mixins import AbstractReportView

from nti.contenttypes.completion.interfaces import IProgress

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.contenttypes.courses.utils import get_context_enrollment_records

from nti.dataserver.authorization import is_admin
from nti.dataserver.authorization import is_site_admin

from nti.namedfile.file import safe_filename

logger = __import__('logging').getLogger(__name__)


class AbstractUserEnrollmentView(AbstractReportView):

    def __init__(self, context, request):
        self.context = context
        self.request = request

        if 'remoteUser' in request.params:
            self.remoteUser = request.params['remoteUser']
        else:
            self.remoteUser = self.getRemoteUser()

        self.options = {}

    def get_user_info(self):
        return self.build_user_info(self.context)

    def _check_access(self):
        if is_admin(self.remoteUser) or self.context == self.remoteUser:
            return True

        if is_site_admin(self.remoteUser):
            admin_utility = component.getUtility(ISiteAdminUtility)
            if admin_utility.can_administer_user(self.remoteUser, self.context):
                return True
        raise HTTPForbidden()

    def get_context_enrollment_records(self):
        return get_context_enrollment_records(self.context, self.remoteUser)

    def _get_enrollment_data(self):
        records = self.get_context_enrollment_records()
        records = sorted(records, key=lambda x:x.createdTime)
        enrollments = []
        for record in records:
            enrollment = {}
            course = ICourseInstance(record)
            catalog_entry = ICourseCatalogEntry(course)
            enrollment["title"] = catalog_entry.title

            enrollment_time = None
            if record.createdTime:
                time = datetime.fromtimestamp(record.createdTime)
                enrollment_time = self._adjust_date(time)
                enrollment["enrollmentTime"] = enrollment_time.strftime("%Y-%m-%d")

            provider = component.getMultiAdapter((self.context, course), ILastSeenProvider)
            accessed_time = self._adjust_date(provider.lastSeenTime) if provider.lastSeenTime else None
            if accessed_time is None:
                accessed_time = enrollment_time

            enrollment["lastAccessed"] = self._format_datetime(accessed_time) if accessed_time else None

            progress = component.queryMultiAdapter((self.context, course),
                                                   IProgress)
            if progress.Completed:
                completed_date = self._adjust_date(progress.CompletedDate)
                completed_date = completed_date.strftime("%Y-%m-%d")
                enrollment["completion"] = completed_date
                enrollment["completionSuccess"] = u'Yes' if progress.CompletedItem.Success else u'No'
            elif progress.PercentageProgress is not None:
                percent = int(progress.PercentageProgress * 100)
                enrollment["completion"] = '%s%%' % percent
                enrollment["completionSuccess"] = u''
            # PercentageProgress returns None if the MaxPossibleProgress is 0
            # or there is no defined MaxPossibleProgress
            else:
                enrollment["completion"] = u'N/A'
                enrollment["completionSuccess"] = u''

            enrollments.append(enrollment)
        return enrollments

    def __call__(self):
        self._check_access()
        return self._do_call()


@view_config(context=IUser,
             request_method='GET',
             name=VIEW_USER_ENROLLMENT,
             accept='application/pdf',
             request_param=not_('format'))
@view_config(context=IUser,
             request_method='GET',
             name=VIEW_USER_ENROLLMENT,
             request_param='format=application/pdf')
class UserEnrollmentReportPdf(AbstractUserEnrollmentView):
    """
    A PDF report of a user's enrollment.
    """

    report_title = _(u'User Enrollment Report')

    @property
    def filename(self):
        result = '%s_%s.pdf' % (self.user_as_affix(self.context), self.request.view_name)
        return safe_filename(result)

    def generate_footer(self):
        date = self._adjust_date(datetime.utcnow())
        date = date.strftime('%b %d, %Y %I:%M %p')
        title = self.report_title
        user = self.context.username
        return u"%s %s %s %s" % (title, user, date, self.timezone_info_str)

    def _do_call(self):
        options = self.options
        options["user"] = self.get_user_info()
        options['enrollments'] = self._get_enrollment_data()
        return options


@view_config(context=IUser,
             request_method='GET',
             name=VIEW_USER_ENROLLMENT,
             accept='text/csv',
             request_param=not_('format'))
@view_config(context=IUser,
             request_method='GET',
             name=VIEW_USER_ENROLLMENT,
             request_param='format=text/csv')
class UserEnrollmentReportCSV(AbstractUserEnrollmentView):
    """
    A CSV report of a user's enrollment.
    """

    def _do_call(self):
        records = self._get_enrollment_data()
        response = self.request.response
        response.content_encoding = 'identity'
        response.content_type = 'text/csv; charset=UTF-8'
        filename = "%s_%s.csv" % (self.user_as_affix(self.context), self.request.view_name)
        response.content_disposition = 'attachment; filename="%s"' % safe_filename(filename)

        stream = BytesIO()
        writer = csv.writer(stream)

        header_row = ['Course Title',
                      'Date Enrolled',
                      'Last Seen (%s)' % self.timezone_util.get_timezone_display_name(),
                      'Completion',
                      'Completed Successfully']

        def _tx_string(s):
            if s is not None and isinstance(s, six.text_type):
                s = s.encode('utf-8')
            return s

        def _write(data, writer, stream):
            writer.writerow([_tx_string(x) for x in data])
            return stream

        _write(header_row, writer, stream)

        for record in records:
            data_row = [record['title'],
                        record['enrollmentTime'],
                        record['lastAccessed'],
                        record['completion'],
                        record['completionSuccess']]
            _write(data_row, writer, stream)

        stream.flush()
        stream.seek(0)
        response.body_file = stream
        return response

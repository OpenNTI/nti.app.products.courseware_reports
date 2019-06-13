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

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import ISiteAdminUtility

from nti.app.products.courseware_reports import MessageFactory as _
from nti.app.products.courseware_reports import VIEW_USER_ENROLLMENT

from nti.app.products.courseware_reports.views.view_mixins import AbstractReportView

from nti.app.products.courseware_reports.views.enrollment_views import EnrollmentViewMixin

from nti.contenttypes.courses.utils import get_context_enrollment_records

from nti.dataserver.authorization import is_admin
from nti.dataserver.authorization import is_site_admin

from nti.namedfile.file import safe_filename

logger = __import__('logging').getLogger(__name__)


class AbstractUserEnrollmentView(AbstractReportView, EnrollmentViewMixin):

    def __init__(self, context, request):
        EnrollmentViewMixin.__init__(self)
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
        return self.build_enrollment_info_for_user(self.context, records=records)

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
        return self._build_filename([self.user_as_affix(self.context), self.report_title])

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

        header_data = (('Name:', options['user'].display or u''),
                       ('Login:', options['user'].username or u''),
                       (self.table_cell(self.timezone_header_str, colspan=2), 'NTI_COLSPAN'))
        header_options = self.get_top_header_options(data=header_data, col_widths=[0.15, 0.85])
        options.update(header_options)
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

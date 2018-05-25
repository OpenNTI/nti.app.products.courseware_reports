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

from collections import namedtuple

from datetime import datetime

from io import BytesIO

from pyramid.config import not_

from pyramid.httpexceptions import HTTPForbidden

from pyramid.view import view_config

from zope import component

from zope.cachedescriptors.property import Lazy

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import ISiteAdminUtility

from nti.app.contenttypes.credit.views import UserAwardedCreditFilterMixin

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports import VIEW_USER_TRANSCRIPT

from nti.app.products.courseware_reports.views.view_mixins import AbstractReportView

from nti.contenttypes.credit.interfaces import ICreditTranscript

from nti.dataserver.authorization import is_admin
from nti.dataserver.authorization import is_site_admin

logger = __import__('logging').getLogger(__name__)


AggregateCredit = namedtuple("AggregateCredit",
                             ('type', 'amount'))


class AbstractUserTranscriptView(AbstractReportView,
                                 UserAwardedCreditFilterMixin):

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

    @Lazy
    def sorted_credits(self):
        awarded_credits = ICreditTranscript(self.context)
        awarded_credits = awarded_credits.iter_awarded_credits()
        awarded_credits = self.filter_credits(awarded_credits)
        return self.sort_credits(awarded_credits)

    def _get_filter_str(self):
        result = []
        if self.definition_type_filter is not None:
            result.append(u'with "%s" type' % self.definition_type_filter)
        if self.definition_units_filter is not None:
            result.append(u'with "%s" units' % self.definition_units_filter)
        if self.not_before is not None:
            not_before = self._adjust_date(self.not_before)
            not_before = not_before.strftime('%B %d, %Y')
            result.append(u'after %s' % not_before)
        if self.not_after is not None:
            not_after = self._adjust_date(self.not_after)
            not_after = not_after.strftime('%B %d, %Y')
            result.append(u'before %s' % not_after)
        if self.amount_filter:
            result.append(u'greater than %s' % self.amount_filter)

        if len(result) == 1:
            result = result[0]
        elif len(result) == 2:
            result = '%s and %s' % (result[0], result[1])
        elif len(result) > 2:
            prefix = ', '.join(result[:-1])
            result = '%s, and %s' % (prefix, result[-1])
        return result

    def _get_credit_amount(self, awarded_credit):
        result = '%.2f %s' % (awarded_credit.amount,
                              awarded_credit.credit_definition.credit_units)
        return result

    def _get_awarded_credits(self):
        result = []
        for awarded_credit in self.sorted_credits:
            awarded_credit_record = {}
            awarded_credit_record['title'] = awarded_credit.title
            awarded_credit_record['issuer'] = awarded_credit.issuer
            awarded_credit_record['type'] = awarded_credit.credit_definition.credit_type
            awarded_credit_record['amount'] = self._get_credit_amount(awarded_credit)
            awarded_date = self._adjust_date(awarded_credit.awarded_date)
            awarded_date = awarded_date.strftime("%Y-%m-%d")
            awarded_credit_record['awarded_date'] = awarded_date
            result.append(awarded_credit_record)
        return result

    def _get_aggregate_credit(self):
        credit_amount_map = {}
        for awarded_credit in self.sorted_credits:
            credit_def = awarded_credit.credit_definition
            current_amount = credit_amount_map.get(credit_def) or 0
            credit_amount_map[credit_def] = current_amount + awarded_credit.amount
        result = [(credit_def, amount) for credit_def, amount in credit_amount_map.items()]
        result = sorted(result, key=lambda x: x[1], reverse=True)
        result = [AggregateCredit(x[0].credit_type, '%.2f %s' % (x[1], x[0].credit_units))
                  for x in result]
        return result

    def __call__(self):
        self._check_access()
        return self._do_call()


@view_config(context=IUser,
             request_method='GET',
             name=VIEW_USER_TRANSCRIPT,
             accept='application/pdf',
             request_param=not_('format'))
@view_config(context=IUser,
             request_method='GET',
             name=VIEW_USER_TRANSCRIPT,
             request_param='format=application/pdf')
class UserTranscriptReportPdf(AbstractUserTranscriptView):
    """
    A PDF report of a user's transcript.
    """

    report_title = _(u'User Transcript Report')

    def generate_footer(self):
        date = self._adjust_date(datetime.utcnow())
        date = date.strftime('%b %d, %Y %I:%M %p')
        title = self.report_title
        user = self.context.username
        return u"%s %s %s %s" % (title, user, date, self.timezone_info_str)

    def _do_call(self):
        options = self.options
        options["user"] = self.get_user_info()
        options['awarded_credits'] = self._get_awarded_credits()
        options['aggregate_credit'] = self._get_aggregate_credit()
        options['filter_str'] = self._get_filter_str()
        return options


@view_config(context=IUser,
             request_method='GET',
             name=VIEW_USER_TRANSCRIPT,
             accept='text/csv',
             request_param=not_('format'))
@view_config(context=IUser,
             request_method='GET',
             name=VIEW_USER_TRANSCRIPT,
             request_param='format=text/csv')
class UserTranscriptReportCSV(AbstractUserTranscriptView):
    """
    A CSV report of a user's transcript.
    """

    def _do_call(self):
        awarded_credits = self._get_awarded_credits()
        response = self.request.response
        response.content_encoding = 'identity'
        response.content_type = 'text/csv; charset=UTF-8'
        filename = "%s_transcript_report.csv" % self.context.username
        response.content_disposition = 'attachment; filename="%s"' % filename

        stream = BytesIO()
        writer = csv.writer(stream)

        header_row = ['Title',
                      'Issuer',
                      'Type',
                      'Amount',
                      'Awarded Date']

        def _tx_string(s):
            if s is not None and isinstance(s, six.text_type):
                s = s.encode('utf-8')
            return s

        def _write(data, writer, stream):
            writer.writerow([_tx_string(x) for x in data])
            return stream

        _write(header_row, writer, stream)

        for awarded_credit in awarded_credits:
            data_row = [awarded_credit['title'],
                        awarded_credit['issuer'],
                        awarded_credit['type'],
                        awarded_credit['amount'],
                        awarded_credit['awarded_date']]
            _write(data_row, writer, stream)

        stream.flush()
        stream.seek(0)
        response.body_file = stream
        return response

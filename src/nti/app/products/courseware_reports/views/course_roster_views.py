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

from zc.displayname.interfaces import IDisplayNameGenerator

from zope import component

from zope.cachedescriptors.property import Lazy

from nti.app.contenttypes.completion.adapters import CompletionContextProgressFactory

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports import VIEW_COURSE_ROSTER
from nti.app.products.courseware_reports import VIEW_ALL_COURSE_ROSTER

from nti.app.products.courseware_reports.interfaces import IRosterReportSupplementalFields

from nti.app.products.courseware_reports.views.view_mixins import AbstractReportView
from nti.app.products.courseware_reports.views.view_mixins import AbstractCourseReportView

from nti.appserver.pyramid_authorization import has_permission

from nti.contenttypes.courses.interfaces import ICourseCatalog
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseEnrollments
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.contenttypes.courses.utils import is_course_instructor

from nti.coremetadata.interfaces import ILastSeenProvider

from nti.dataserver.authorization import ACT_CONTENT_EDIT

from nti.dataserver.authorization import is_admin_or_site_admin

from nti.dataserver.users.interfaces import IFriendlyNamed

from nti.dataserver.users.users import User

from nti.mailer.interfaces import IEmailAddressable

from nti.namedfile.file import safe_filename

logger = __import__('logging').getLogger(__name__)


CatalogEntryRecord = \
    namedtuple('CatalogEntryRecord',
               ('title', 'start_date', 'instructors', 'provider_unique_id'))


class RosterReportMixin(AbstractReportView):

    def _name(self, user, friendly_named=None):
        displayname = component.getMultiAdapter((user, self.request),
                                                IDisplayNameGenerator)()

        if not friendly_named:
            friendly_named = IFriendlyNamed(user)

        if friendly_named.realname and displayname != friendly_named.realname:
            displayname = '%s (%s)' % (friendly_named.realname, displayname)
        return displayname

    @Lazy
    def supplemental_field_utility(self):
        return component.queryUtility(IRosterReportSupplementalFields)

    def _build_enrollment_info(self, course):
        enrollments = []
        required_item_providers = None
        course_enrollments = ICourseEnrollments(course)
        for record in course_enrollments.iter_enrollments():
            enrollRecord = {}

            user = User.get_user(record.Principal)
            if user is None:
                # Deleted user
                continue

            progress_factory = CompletionContextProgressFactory(user,
                                                                course,
                                                                required_item_providers)
            progress = progress_factory()
            if required_item_providers is None:
                required_item_providers = progress_factory.required_item_providers

            if progress.Completed:
                completed_date = self._adjust_date(progress.CompletedDate)
                completed_date = completed_date.strftime(u"%Y-%m-%d")
                enrollRecord["completion"] = completed_date
            elif progress.PercentageProgress is not None:
                percent = int(progress.PercentageProgress * 100)
                enrollRecord["completion"] = u'%s%%' % percent
            # PercentageProgress returns None if the MaxPossibleProgress is 0
            # or there is no defined MaxPossibleProgress
            else:
                enrollRecord["completion"] = u'N/A'

            enrollRecord["username"] = user.username

            fn_user = IFriendlyNamed(user)
            enrollRecord["displayname"] = self._name(user, friendly_named=fn_user)

            email_addressable = IEmailAddressable(user, None)
            enrollRecord["email"] = email_addressable.email if email_addressable else None

            enrollment_time = None
            if record.createdTime:
                time = datetime.utcfromtimestamp(record.createdTime)
                enrollment_time = self._adjust_date(time)
                enrollRecord["enrollmentTime"] = enrollment_time.strftime(u"%Y-%m-%d")

            provider = component.getMultiAdapter((user, course), ILastSeenProvider)
            accessed_time = self._adjust_date(provider.lastSeenTime) if provider.lastSeenTime else enrollment_time

            enrollRecord["lastAccessed"] = self._format_datetime(accessed_time) if accessed_time else None
            if self.supplemental_field_utility:
                user_supp_data = self.supplemental_field_utility.get_user_fields(user)
                if user_supp_data:
                    enrollRecord.update(user_supp_data)

            enrollments.append(enrollRecord)

        return enrollments


class AbstractCourseRosterReport(AbstractCourseReportView,
                                 RosterReportMixin):

    def __init__(self, context, request):
        self.context = context
        self.request = request

        if 'remoteUser' in request.params:
            self.remoteUser = request.params['remoteUser']
        else:
            self.remoteUser = self.getRemoteUser()

        self.options = {}


@view_config(context=ICourseInstance,
             request_method='GET',
             name=VIEW_COURSE_ROSTER,
             accept='application/pdf',
             request_param=not_('format'))
@view_config(context=ICourseInstance,
             request_method='GET',
             name=VIEW_COURSE_ROSTER,
             request_param='format=application/pdf')
class CourseRosterReportPdf(AbstractCourseRosterReport):
    """
    A PDF report of a course's roster.
    """

    report_title = _(u'Course Roster Report')

    @property
    def filename(self):
        result = '%s_course_roster_report.pdf' % self.course_name()
        return safe_filename(result)

    def __call__(self):
        self._check_access()
        options = self.options
        enrollments = self._build_enrollment_info(self.course)
        options["enrollments"] = enrollments
        options["TotalEnrolledCount"] = len(enrollments)
        return options


class AbstractAllCourseReport(RosterReportMixin):

    def report_description(self):
        return u"This report presents the roster of all courses."

    def _check_access(self):
        if not is_admin_or_site_admin(self.remoteUser):
            raise HTTPForbidden()

    def _get_title(self, entry):
        return entry.title or u'<Empty title>'

    def _get_instructors_str(self, entry):
        names = [x.Name for x in entry.Instructors or ()]
        return u', '.join(names)

    def _get_start_date(self, entry):
        result = entry.StartDate
        if result is not None:
            result = result.strftime('%b %d, %Y')
        return result

    def _make_entry_record(self, entry):
        start_date = self._get_start_date(entry)
        instructors = self._get_instructors_str(entry)
        title = self._get_title(entry)
        return CatalogEntryRecord(title,
                                  start_date,
                                  instructors,
                                  provider_unique_id=entry.ProviderUniqueID)

    def _is_entry_visible(self, entry):
        # XXX: Should this be in the catalog iterator itself?
        # Instructor (who is also child site admin) in section course has read permission to its parent course.
        return has_permission(ACT_CONTENT_EDIT, entry) or is_course_instructor(entry, self.remoteUser)

    def _get_entries_and_courses(self):
        """
        Return a sorted, deduped set of course objects.
        """
        entries = set()
        catalog = component.queryUtility(ICourseCatalog)
        if catalog is not None:
            for entry in catalog.iterCatalogEntries():
                if self._is_entry_visible(entry):
                    entries.add(entry)

        def sort_key(entry_obj):
            title = entry_obj.title
            start = entry_obj.StartDate
            return (title is not None, title, start is not None, start)
        entries = sorted(entries, key=sort_key)
        result = []
        for entry in entries:
            course = ICourseInstance(entry, None)
            if course is not None:
                entry_record = self._make_entry_record(entry)
                result.append((entry_record, course))
        return result

    def _get_course_instructors(self, course):
        entry = ICourseCatalogEntry(course)
        if entry is not None:
            return entry.Instructors


@view_config(context=ICourseCatalog,
             request_method='GET',
             name=VIEW_ALL_COURSE_ROSTER,
             accept='application/pdf',
             request_param=not_('format'))
@view_config(context=ICourseCatalog,
             request_method='GET',
             name=VIEW_ALL_COURSE_ROSTER,
             request_param='format=application/pdf')
class AllCourseRosterReportPdf(AbstractAllCourseReport):
    """
    A PDF report of all course rosters.
    """

    report_title = _(u'All Course Roster Report')

    def __call__(self):
        self._check_access()
        options = self.options
        records = []
        entries_courses = self._get_entries_and_courses()
        for entry, course in entries_courses:
            enrollments = self._build_enrollment_info(course)
            records.append((entry, enrollments))
        options["course_records"] = records
        options["TotalCourseCount"] = len(records)
        return options


@view_config(context=ICourseInstance,
             request_method='GET',
             name=VIEW_COURSE_ROSTER,
             accept='text/csv',
             request_param=not_('format'))
@view_config(context=ICourseInstance,
             request_method='GET',
             name=VIEW_COURSE_ROSTER,
             request_param='format=text/csv')
class CourseRosterReportCSV(AbstractCourseRosterReport):
    """
    A CSV report of a course roster.
    """

    def __call__(self):
        self._check_access()
        enrollments = self._build_enrollment_info(self.course)

        response = self.request.response
        response.content_encoding = 'identity'
        response.content_type = 'text/csv; charset=UTF-8'
        filename = '%s_course_roster_report.csv' % self.course_name()
        response.content_disposition = 'attachment; filename="%s"' % safe_filename(filename)

        stream = BytesIO()
        writer = csv.writer(stream)

        header_row = ['Name', 'User Name', 'Email',
                      'Date Enrolled',
                      'Last Seen',
                      'Completion']
        if self.supplemental_field_utility:
            display_dict = self.supplemental_field_utility.get_field_display_values()
            supp_fields = self.supplemental_field_utility.get_ordered_fields()
            for supp_field in supp_fields:
                header_row.append(display_dict.get(supp_field))

        def _tx_string(s):
            if s is not None and isinstance(s, six.text_type):
                s = s.encode('utf-8')
            return s

        def _write(data, writer, stream):
            writer.writerow([_tx_string(x) for x in data])
            return stream

        _write(header_row, writer, stream)

        for record in enrollments:
            data_row = [record['displayname'],
                        record['username'],
                        record['email'],
                        record['enrollmentTime'],
                        record['lastAccessed'],
                        record['completion']]

            if self.supplemental_field_utility:
                supp_fields = self.supplemental_field_utility.get_ordered_fields()
                for supp_field in supp_fields:
                    data_row.append(record.get(supp_field))
            _write(data_row, writer, stream)

        stream.flush()
        stream.seek(0)
        response.body_file = stream
        return response


@view_config(context=ICourseCatalog,
             request_method='GET',
             name=VIEW_ALL_COURSE_ROSTER,
             accept='text/csv',
             request_param=not_('format'))
@view_config(context=ICourseCatalog,
             request_method='GET',
             name=VIEW_ALL_COURSE_ROSTER,
             request_param='format=text/csv')
class AllCourseRosterReportCSV(AbstractAllCourseReport):
    """
    A CSV report of all course rosters.
    """

    def __call__(self):
        self._check_access()
        response = self.request.response
        response.content_encoding = 'identity'
        response.content_type = 'text/csv; charset=UTF-8'
        response.content_disposition = 'attachment; filename="all_course_roster_report.csv"'

        stream = BytesIO()
        writer = csv.writer(stream)

        header_row = ['Course Name', 'Course Provider Unique ID', 'Course Start Date',
                      'Course Instructors',
                      'Name', 'User Name', 'Email',
                      'Date Enrolled',
                      'Last Seen',
                      'Completion']

        if self.supplemental_field_utility:
            display_dict = self.supplemental_field_utility.get_field_display_values()
            supp_fields = self.supplemental_field_utility.get_ordered_fields()
            for supp_field in supp_fields:
                header_row.append(display_dict.get(supp_field))

        def _tx_string(s):
            if s is not None and isinstance(s, six.text_type):
                s = s.encode('utf-8')
            return s

        def _write(data, writer, stream):
            writer.writerow([_tx_string(x) for x in data])
            return stream

        _write(header_row, writer, stream)

        entries_courses = self._get_entries_and_courses()
        for entry, course in entries_courses:
            enrollments = self._build_enrollment_info(course)
            for record in enrollments:
                data_row = [entry.title,
                            entry.provider_unique_id,
                            entry.start_date,
                            entry.instructors,
                            record['displayname'],
                            record['username'],
                            record['email'],
                            record['enrollmentTime'],
                            record['lastAccessed'],
                            record['completion']]

                if self.supplemental_field_utility:
                    supp_fields = self.supplemental_field_utility.get_ordered_fields()
                    for supp_field in supp_fields:
                        data_row.append(record.get(supp_field))
                _write(data_row, writer, stream)

        stream.flush()
        stream.seek(0)
        response.body_file = stream
        return response

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import gevent

from pyramid.config import not_

from pyramid.httpexceptions import HTTPForbidden

from pyramid.view import view_config

from zope.cachedescriptors.property import Lazy

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports import VIEW_COURSE_ROSTER
from nti.app.products.courseware_reports import VIEW_ALL_COURSE_ROSTER

from nti.app.products.courseware_reports.views.view_mixins import AbstractReportView
from nti.app.products.courseware_reports.views.view_mixins import AbstractCourseReportView

from nti.app.products.courseware_reports.views.enrollment_views import EnrollmentViewMixin
from nti.app.products.courseware_reports.views.enrollment_views import EnrollmentReportCSVMixin

from nti.appserver.pyramid_authorization import has_permission

from nti.contenttypes.courses.interfaces import ICourseCatalog
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.contenttypes.courses.utils import is_course_instructor

from nti.dataserver.authorization import ACT_CONTENT_EDIT

from nti.dataserver.authorization import is_admin_or_site_admin

from nti.namedfile.file import safe_filename

logger = __import__('logging').getLogger(__name__)


class AbstractCourseRosterReport(AbstractCourseReportView,
                                 EnrollmentViewMixin):

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
        enrollments = self.build_enrollment_info_for_course(self.course)
        options["enrollments"] = enrollments
        options["TotalEnrolledCount"] = len(enrollments)

        header_options = self._get_top_header_options()
        options.update(header_options)
        return options


class AbstractAllCourseReport(AbstractReportView, EnrollmentViewMixin):

    def report_description(self):
        return u"This report presents the roster of all courses."

    def _check_access(self):
        if not is_admin_or_site_admin(self.remoteUser):
            raise HTTPForbidden()

    def _is_entry_visible(self, entry, course=None):
        # XXX: Should this be in the catalog iterator itself?
        # Instructor (who is also child site admin) in section course has read permission to its parent course.
        return has_permission(ACT_CONTENT_EDIT, entry) \
            or is_course_instructor(entry, self.remoteUser)


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
            gevent.sleep()
            enrollments = self.build_enrollment_info_for_course(course)
            records.append((entry, enrollments))
        options["course_records"] = records
        options["TotalCourseCount"] = len(records)

        data = [(self.report_description(),),
                (self.timezone_header_str,)]
        header_options = self.get_top_header_options(data=data,
                                                     col_widths=[1])
        options.update(header_options)
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
class CourseRosterReportCSV(AbstractCourseRosterReport, EnrollmentReportCSVMixin):
    """
    A CSV report of a course roster.
    """

    @Lazy
    def header_field_map(self):
        return {
            'Course Name': 'title', # all course roster report.
            'Course Title': 'title',
            'Course Provider Unique ID': 'provider_unique_id',
            'Course Start Date': 'start_date',
            'Course Instructors': 'instructors',

            'Name': 'displayname',
            'User Name': 'username',
            'Email': 'email',

            'Date Enrolled': 'enrollmentTime',
            'Last Seen (%s)' % self.timezone_util.get_timezone_display_name(): 'lastAccessed',
            'Completion': 'completion',
            'Completed Successfully': 'completionSuccess',
            'Completion Percentage': 'completionPercentage',
            'Completion Date': 'completionDate'
        }

    @Lazy
    def header_row(self):
        return ['Name', 'User Name', 'Email',
                'Date Enrolled',
                'Last Seen (%s)' % self.timezone_util.get_timezone_display_name(),
                'Completion',
                'Completed Successfully',
                'Completion Percentage',
                'Completion Date']

    @Lazy
    def groupByCourse(self):
        return True

    @Lazy
    def show_supplemental_info(self):
        return self.groupByCourse

    def _get_enrollment_data(self):
        entry = ICourseCatalogEntry(self.course)
        entry_record = self._make_entry_record(entry)
        enrollments = self.build_enrollment_info_for_course(self.course)
        return ((entry_record, enrollments),)

    def __call__(self):
        self._check_access()
        filename = '%s_course_roster_report.csv' % self.course_name()
        return self._do_create_response(filename=safe_filename(filename))


@view_config(context=ICourseCatalog,
             request_method='GET',
             name=VIEW_ALL_COURSE_ROSTER,
             accept='text/csv',
             request_param=not_('format'))
@view_config(context=ICourseCatalog,
             request_method='GET',
             name=VIEW_ALL_COURSE_ROSTER,
             request_param='format=text/csv')
class AllCourseRosterReportCSV(AbstractAllCourseReport, EnrollmentReportCSVMixin):
    """
    A CSV report of all course rosters.
    """

    @Lazy
    def header_field_map(self):
        return {
            'Course Name': 'title', # all course roster report.
            'Course Title': 'title',
            'Course Provider Unique ID': 'provider_unique_id',
            'Course Start Date': 'start_date',
            'Course Instructors': 'instructors',

            'Name': 'displayname',
            'User Name': 'username',
            'Email': 'email',

            'Date Enrolled': 'enrollmentTime',
            'Last Seen (%s)' % self.timezone_util.get_timezone_display_name(): 'lastAccessed',
            'Completion': 'completion',
            'Completed Successfully': 'completionSuccess',
            'Completion Percentage': 'completionPercentage',
            'Completion Date': 'completionDate'
        }

    @Lazy
    def header_row(self):
        return ['Course Name', 'Course Provider Unique ID', 'Course Start Date',
                'Course Instructors',
                'Name', 'User Name', 'Email',
                'Date Enrolled',
                'Last Seen (%s)' % self.timezone_util.get_timezone_display_name(),
                'Completion',
                'Completed Successfully',
                'Completion Percentage',
                'Completion Date']

    @Lazy
    def groupByCourse(self):
        return True

    @Lazy
    def show_supplemental_info(self):
        return self.groupByCourse

    def _get_enrollment_data(self):
        result = []
        entries_courses = self._get_entries_and_courses()
        for entry_record, course in entries_courses:
            gevent.sleep()
            enrollments = self.build_enrollment_info_for_course(course)
            result.append((entry_record, enrollments))
        return result

    def __call__(self):
        self._check_access()
        return self._do_create_response(filename='all_course_roster_report.csv')

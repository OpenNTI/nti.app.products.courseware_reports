#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import gevent

from datetime import datetime
from datetime import timedelta

from pyramid.config import not_

from pyramid.httpexceptions import HTTPForbidden

from pyramid.view import view_config

from zope import component

from zope.intid.interfaces import IIntIds

from zope.cachedescriptors.property import Lazy

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports import VIEW_COURSE_ROSTER
from nti.app.products.courseware_reports import VIEW_ALL_COURSE_ROSTER

from nti.app.products.courseware_reports.views.view_mixins import AbstractCourseReportView

from nti.app.products.courseware_reports.views.enrollment_views import EnrollmentViewMixin
from nti.app.products.courseware_reports.views.enrollment_views import AbstractEnrollmentReport
from nti.app.products.courseware_reports.views.enrollment_views import EnrollmentReportCSVMixin

from nti.appserver.pyramid_authorization import has_permission

from nti.contenttypes.completion.interfaces import ICompletionContext

from nti.contenttypes.completion.utils import get_indexed_completed_items_intids

from nti.contenttypes.courses.interfaces import IDeletedCourse
from nti.contenttypes.courses.interfaces import ICourseCatalog
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.contenttypes.courses.utils import is_course_instructor

from nti.dataserver.authorization import ACT_CONTENT_EDIT

from nti.dataserver.authorization import is_admin_or_site_admin

from nti.dataserver.users import User

from nti.namedfile.file import safe_filename


logger = __import__('logging').getLogger(__name__)


class AbstractCourseRosterReport(AbstractCourseReportView,
                                 EnrollmentViewMixin):
    
    report_title = _(u'Course Roster Report')

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

    @property
    def filename(self):
        return self._build_filename([self.course_title(), self.course_id(), self.report_title])

    def __call__(self):
        self._check_access()
        options = self.options
        enrollments = self.build_enrollment_info_for_course(self.course)
        options["enrollments"] = enrollments
        options["TotalEnrolledCount"] = len(enrollments)

        header_options = self._get_top_header_options()
        options.update(header_options)
        return options


class AbstractAllCourseReport(AbstractEnrollmentReport):

    def report_description(self):
        return u"This report presents the roster of all courses."

    def _check_access(self):
        if not is_admin_or_site_admin(self.remoteUser):
            raise HTTPForbidden()

    def _is_entry_visible(self, entry, course=None):
        # XXX: Should this be in the catalog iterator itself?
        # Instructor (who is also child site admin) in section course has read permission to its parent course.
        course = course or ICourseInstance(entry, None)
        return not IDeletedCourse.providedBy(course) \
            and (   has_permission(ACT_CONTENT_EDIT, entry) \
                 or is_course_instructor(entry, self.remoteUser))

    DEFAULT_COMPLETION_NOT_BEFORE_DAY_COUNT = 365

    @property
    def default_completion_not_before(self):
        """
        By default, limit these all-encompassing reports to the past calendar
        year.
        """
        delta = timedelta(days=self.DEFAULT_COMPLETION_NOT_BEFORE_DAY_COUNT)
        return datetime.utcnow() - delta

    def _get_enrollment_data(self):
        """
        As a shortcut, use completed items in our time range as a hint to which
        users may have completed courses in that window.

        Ideally, we move towards persistent course completion and lookup in the
        near future.
        """
        # Start by getting all completed items within our window
        completed_intids = get_indexed_completed_items_intids(min_time=self.completionNotBefore,
                                                              max_time=self.completionNotAfter,
                                                              by_day=True)
        intids = component.getUtility(IIntIds)
        seen = set()
        entry_ntiid_to_course_users = dict()
        for completed_intid in completed_intids:
            completed_item = intids.queryObject(completed_intid)
            if completed_item is None:
                continue
            user_id = completed_item.Principal.id
            context = ICompletionContext(completed_item, None)
            course = ICourseInstance(context, None)
            entry = ICourseCatalogEntry(course, None)
            if entry is None:
                continue
            entry_ntiid = entry.ntiid
            key = (user_id, entry_ntiid)
            if key in seen:
                continue
            seen.add(key)
            if entry_ntiid not in entry_ntiid_to_course_users:
                entry_ntiid_to_course_users[entry_ntiid] = (course, [])
            user = User.get_user(user_id)
            entry_ntiid_to_course_users[entry_ntiid][1].append(user)
        result = []
        for course_users in entry_ntiid_to_course_users.values():
            gevent.sleep()
            course, users = course_users
            entry = ICourseCatalogEntry(course)
            entry_record = self._make_entry_record(entry)
            enrollments = self.build_enrollment_info_for_course(course,
                                                                included_users=users)
            result.append((entry_record, enrollments))
        return result


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
        records = self._get_enrollment_data()
        options["TotalCourseCount"] = len(records)
        # Only those courses with enrollments.
        records = [x for x in records if x[1]]
        options["course_records"] = records

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
            'Deactivated': 'deactivated',

            'Date Enrolled': 'enrollmentTime',
            'Last Seen (%s)' % self.timezone_util.get_timezone_display_name(): 'lastAccessed',
            'Completion': 'completion',
            'Completed Successfully': 'completionSuccess',
            'Completion Percentage': 'completionPercentage',
            'Completion Date': 'completionDate'
        }

    @Lazy
    def header_row(self):
        return ['Name', 'User Name', 'Email', 'Deactivated',
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
        filename = self._build_filename([self.course_title(), self.course_id(), self.report_title], extension=".csv")
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
            'Deactivated': 'deactivated',

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
                'Name', 'User Name', 'Email', 'Deactivated',
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

    def __call__(self):
        self._check_access()
        return self._do_create_response(filename='all_course_roster_report.csv')

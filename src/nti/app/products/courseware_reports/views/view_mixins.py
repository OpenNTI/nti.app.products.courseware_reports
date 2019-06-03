#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from datetime import datetime

from pyramid.httpexceptions import HTTPForbidden

from zope.cachedescriptors.property import Lazy

from zope.security.management import checkPermission

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.contenttypes.reports.views.view_mixins import AbstractReportView

from nti.app.products.courseware_reports.interfaces import ACT_VIEW_REPORTS

from nti.app.products.courseware_reports.views import ALL_USERS

from nti.contenttypes.courses.interfaces import ES_PUBLIC
from nti.contenttypes.courses.interfaces import ES_CREDIT

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.contenttypes.courses.utils import get_course_enrollments

from nti.dataserver.authorization import is_admin_or_site_admin

from nti.dataserver.interfaces import IEnumerableEntityContainer

from nti.dataserver.users.interfaces import IFriendlyNamed

from nti.namedfile.file import safe_filename

logger = __import__('logging').getLogger(__name__)


def _get_enrollment_scope_dict(course, instructors=set()):
    """
    Build a dict of scope_name to usernames.
    """
    # XXX: We are not exposing these multiple scopes in many places,
    # including many reports and in TopCreators.

    # XXX: This is confusing if we are nesting scopes.  Perhaps
    # it makes more sense to keep things in the Credit/NonCredit camps.
    # Seems like it would make sense to have an Everyone scope...
    # { Everyone: { Public : ( Open, Purchased ), ForCredit : ( FCD, FCND ) }}

    # XXX: This automatically rolls up students in sub-sections into
    # this report (if the sub-students are in the super's scopes). It's been
    # like this for a while, but it seems confusing unless the instructor
    # is aware they are looking at a super-course, which is not displayed
    # in any way I can see.
    results = {}
    # Lumping purchased in with public.
    public_scope = course.SharingScopes.get('Public', None)
    purchased_scope = course.SharingScopes.get('Purchased', None)
    non_public_users = set()
    for scope_name in course.SharingScopes:
        scope = course.SharingScopes.get(scope_name, None)
        if scope is not None and scope not in (public_scope, purchased_scope):
            # If our scope is not 'public'-ish, store it separately.
            # All credit-type users should end up in ForCredit.
            scope_users = {
                x.lower() for x in IEnumerableEntityContainer(scope).iter_usernames()
            }
            scope_users = scope_users - instructors
            results[scope_name] = scope_users
            non_public_users = non_public_users.union(scope_users)

    all_users = {
        x.lower() for x in IEnumerableEntityContainer(public_scope).iter_usernames()
    }
    results['Public'] = all_users - non_public_users - instructors
    results[ALL_USERS] = all_users
    return results


class AbstractCourseReportView(AbstractReportView):
    """
    An abstract report view that can be used on something that can be adapted
    to an :class:`ICourseInstance`.
    """
    @property
    def filename(self):
        return self._build_filename([self.course_name(), self.report_title])

    def _check_access(self):
        if is_admin_or_site_admin(self.remoteUser):
            return True

        if not checkPermission(ACT_VIEW_REPORTS.id, self.course):
            raise HTTPForbidden()

    @Lazy
    def course(self):
        return ICourseInstance(self.context)

    @Lazy
    def course_start_date(self):
        try:
            # legacy code path, but faster
            entry = self.course.legacy_catalog_entry
        except AttributeError:
            entry = ICourseCatalogEntry(self.course)
        return entry.StartDate

    # Making all of these include lowercase names
    @Lazy
    def instructor_usernames(self):
        return {x.id.lower() for x in self.course.instructors}

    @Lazy
    def _get_enrollment_scope_dict(self):
        """
        Build a dict of scope_name to usernames.
        """
        # XXX: We are not exposing these multiple scopes in many places,
        # including many reports and in TopCreators.
        # XXX: This is confusing if we are nesting scopes.  Perhaps
        # it makes more sense to keep things in the Credit/NonCredit camps.
        return _get_enrollment_scope_dict(self.course, self.instructor_usernames)

    @Lazy
    def _scope_alias_dict(self):
        """
        A dict of scope_name -> scope_alias.
        """
        result = dict()
        for scope in self.course.SharingScopes.values():
            scope_alias = IFriendlyNamed(scope).alias
            result[scope.__name__] = scope_alias
        return result

    @Lazy
    def intids_created_by_students(self):
        return self.md_catalog['creator'].apply({'any_of': self.all_student_usernames})

    @Lazy
    def intids_created_by_everyone(self):
        return self.md_catalog['creator'].apply({'any_of': self.all_usernames})

    @Lazy
    def intids_created_by_everyone_enrolled_in_course(self):
        return self.md_catalog['creator'].apply({'any_of': self.all_usernames_enrolled_in_course})

    def for_credit_scope_name(self):
        return self._scope_alias_dict[ES_CREDIT]

    def non_credit_scope_name(self):
        return self._scope_alias_dict[ES_PUBLIC]

    def _get_users_for_scope(self, scope_name):
        """
        Returns a set of users for the given scope_name, or None if that scope does not exist.
        """
        scope_dict = self._get_enrollment_scope_dict
        return scope_dict[scope_name]

    @Lazy
    def for_credit_student_usernames(self):
        return self._get_users_for_scope(ES_CREDIT)

    @Lazy
    def open_student_usernames(self):
        return self.all_student_usernames - self.for_credit_student_usernames

    @Lazy
    def all_student_usernames(self):
        return self.all_usernames - self.instructor_usernames

    @Lazy
    def all_usernames(self):
        return self._get_users_for_scope(ALL_USERS)

    @Lazy
    def all_usernames_enrolled_in_course(self):
        enrollments = get_course_enrollments(self.course)
        usernames = [enrollment.Principal.username for enrollment in enrollments]
        return usernames

    @Lazy
    def count_all_students(self):
        return len(self.all_student_usernames)

    @Lazy
    def count_credit_students(self):
        return len(self.for_credit_student_usernames)

    @Lazy
    def count_non_credit_students(self):
        return len(self.open_student_usernames)

    @Lazy
    def all_user_intids(self):
        ids = self.family.II.TreeSet()
        scope = self.course.SharingScopes['Public']
        ids.update(IEnumerableEntityContainer(scope).iter_intids())
        return ids

    def course_name(self):
        catalog_entry = ICourseCatalogEntry(self.course, None)
        result = catalog_entry.ProviderUniqueID if catalog_entry else self.course.__name__
        return result

    def generate_footer(self):
        date = self._adjust_date(datetime.utcnow())
        date = date.strftime('%b %d, %Y %I:%M %p')
        title = self.report_title
        course = self.course_name()
        return "%s %s %s %s" % (title, course, date, self.timezone_info_str)

    def generate_semester(self):
        """
        Generate the semester suffix used in report metadata.
        """
        return generate_semester(start_date=self.course_start_date)

    def _get_additional_header_data(self):
        return ()

    def _get_top_header_options(self, col_widths=[0.2, 0.8]):
        data = []
        data.extend(self._get_additional_header_data())
        data.extend([('Course:', self.course_name()),
                     (self.table_cell(self.timezone_header_str, colspan=2), 'NTI_COLSPAN')])
        return self.get_top_header_options(data=data,
                                           col_widths=col_widths)


def generate_semester(entry=None, start_date=None):
    """
    Generate the semester suffix used in report metadata.
    """
    start_date = entry.StartDate if not start_date and entry else start_date
    start_month = start_date.month if start_date else None
    if start_month < 5:
        semester = _(u'Spring')
    elif start_month < 8:
        semester = _(u'Summer')
    else:
        semester = _(u'Fall')

    start_year = start_date.year if start_date else None
    return u'- %s %s' % (semester, start_year) if start_date else ''

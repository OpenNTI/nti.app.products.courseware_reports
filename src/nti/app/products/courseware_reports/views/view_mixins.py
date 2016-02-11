#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import textwrap
from datetime import datetime
from collections import namedtuple

from zope import component
from zope import interface

from pyramid.view import view_defaults
from pyramid.httpexceptions import HTTPForbidden

from z3c.pagelet.browser import BrowserPagelet

from zope.catalog.interfaces import ICatalog

from zope.intid.interfaces import IIntIds

from zope.security.management import checkPermission

import BTrees

from nti.common.property import Lazy

from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.dataserver.authorization import ACT_READ

from nti.dataserver.interfaces import IDeletedObjectPlaceholder
from nti.dataserver.interfaces import IUsernameSubstitutionPolicy
from nti.dataserver.interfaces import IEnumerableEntityContainer

from nti.dataserver.users.users import User
from nti.dataserver.users.interfaces import IFriendlyNamed

from nti.dataserver.metadata_index import CATALOG_NAME

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports.interfaces import IPDFReportView

from nti.app.products.courseware_reports.interfaces import ACT_VIEW_REPORTS

from nti.app.products.courseware_reports.reports import _adjust_date

from nti.app.products.courseware_reports.views import ALL_USERS

class _StudentInfo(namedtuple('_StudentInfo',
							  ('display', 'username', 'count', 'perc'))):
	"""
	Holds general student info. 'count' and 'perc' are optional values
	"""

	def __new__(cls, display, username, count=None, perc=None):
		return super(_StudentInfo, cls).__new__(cls, display, username, count, perc)

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
			scope_users = {x.lower() for x in IEnumerableEntityContainer(scope).iter_usernames()}
			scope_users = scope_users - instructors
			results[scope_name] = scope_users
			non_public_users = non_public_users.union(scope_users)

	all_users = {x.lower() for x in IEnumerableEntityContainer(public_scope).iter_usernames()}
	results['Public'] = all_users - non_public_users - instructors
	results[ALL_USERS] = all_users
	return results

@view_defaults(route_name='objects.generic.traversal',
			   renderer="../templates/std_report_layout.rml",
			   request_method='GET',
			   permission=ACT_READ)
@interface.implementer(IPDFReportView)
class _AbstractReportView(AbstractAuthenticatedView,
						  BrowserPagelet):

	family = BTrees.family64

	def __init__(self, context, request):
		self.options = {}
		# Our two parents take different arguments
		AbstractAuthenticatedView.__init__(self, request)
		BrowserPagelet.__init__(self, context, request)

		if request.view_name:
			self.filename = request.view_name

	def _check_access(self):
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

	@Lazy
	def md_catalog(self):
		return component.getUtility(ICatalog, CATALOG_NAME)

	@Lazy
	def uidutil(self):
		return component.getUtility(IIntIds)

	@Lazy
	def intids_created_by_students(self):
		return self.md_catalog['creator'].apply({'any_of': self.all_student_usernames})

	@Lazy
	def intids_created_by_everyone(self):
		return self.md_catalog['creator'].apply({'any_of': self.all_usernames})

	# Making all of these include lowercase names
	@Lazy
	def instructor_usernames(self):
		return {x.id.lower() for x in self.course.instructors}

	@Lazy
	def _get_enrollment_scope_dict(self):
		"""
		Build a dict of scope_name to usernames.
		"""
		# XXX We are not exposing these multiple scopes in many places,
		# including many reports and in TopCreators.
		# XXX This is confusing if we are nesting scopes.  Perhaps
		# it makes more sense to keep things in the Credit/NonCredit camps.
		return _get_enrollment_scope_dict(self.course, self.instructor_usernames)

	def _get_users_for_scope(self, scope_name):
		"""
		Returns a set of users for the given scope_name, or None if that scope does not exist.
		"""
		scope_dict = self._get_enrollment_scope_dict
		return scope_dict[scope_name]

	@Lazy
	def for_credit_student_usernames(self):
		return self._get_users_for_scope('ForCredit')

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
		ids.update(IEnumerableEntityContainer(self.course.SharingScopes['Public']).iter_intids())
		return ids

	def get_student_info(self, username):
		"""
		Given a username, return a _StudentInfo tuple
		"""
		# Actually, the `creator` field is meant to hold an arbitrary
		# entity. If it is a user, User.get_user simply returns it.
		# If it's some other entity object, default to 'System'.
		try:
			user = User.get_user(username)
		except TypeError:
			user = None
			username = 'System'
		if user:
			return self.build_user_info(user)
		return _StudentInfo(username, username)

	def _replace_username(self, username):
		policy = component.queryUtility(IUsernameSubstitutionPolicy)
		result = policy.replace(username) if policy else username
		return result

	def build_user_info(self, user):
		"""
		Given a user, return a _StudentInfo tuple
		"""
		named_user = IFriendlyNamed(user)
		display_name = named_user.alias or named_user.realname or named_user.username

		username = ""
		# Do not display username of open students
		if user.username.lower() in self.for_credit_student_usernames:
			username = self._replace_username(user.username)

		return _StudentInfo(display_name, username)

	def filter_objects(self, objects):
		"""
		Returns a set of filtered objects
		"""
		return [ x for x in objects
				if not IDeletedObjectPlaceholder.providedBy(x) ]

	def course_name(self):
		catalog_entry = ICourseCatalogEntry(self.course, None)
		result = catalog_entry.ProviderUniqueID if catalog_entry else self.course.__name__
		return result

	def generate_footer(self):
		date = _adjust_date(datetime.utcnow())
		date = date.strftime('%b %d, %Y %I:%M %p')
		title = self.report_title
		course = self.course_name()
		student = getattr(self, 'student_user', '')
		return "%s %s %s %s" % (title, course, student, date)

	def generate_semester(self):
		start_date = self.course_start_date
		start_month = start_date.month if start_date else None
		if start_month < 5:
			semester = _('Spring')
		elif start_month < 8:
			semester = _('Summer')
		else:
			semester = _('Fall')

		start_year = start_date.year if start_date else None
		return '%s %s' % (semester, start_year) if start_date else ''

	def wrap_text(self, text, size):
		return textwrap.fill(text, size)

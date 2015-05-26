#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from . import MessageFactory as _

from zope import interface
from zope import component

from zope.security.management import checkPermission

from pyramid.interfaces import IRequest

from nti.assessment.interfaces import IQAssignment

from nti.app.renderers.decorators import AbstractAuthenticatedRequestAwareDecorator

from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment
from nti.app.products.gradebook.interfaces import IGradeBook

from nti.contentlibrary.interfaces import IContentPackage

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry
from nti.contenttypes.courses.interfaces import ICourseAdministrativeLevel

from nti.dataserver.contenttypes.forums.interfaces import ICommunityForum
from nti.dataserver.contenttypes.forums.interfaces import ICommunityHeadlineTopic

from nti.externalization.interfaces import StandardExternalFields
from nti.externalization.interfaces import IExternalMappingDecorator

from nti.links.links import Link

from nti.traversal.traversal import find_interface

from .interfaces import ACT_VIEW_REPORTS

from . import VIEW_COURSE_SUMMARY
from . import VIEW_ASSIGNMENT_SUMMARY
from . import VIEW_FORUM_PARTICIPATION
from . import VIEW_TOPIC_PARTICIPATION
from . import VIEW_STUDENT_PARTICIPATION

LINKS = StandardExternalFields.LINKS

class _AbstractInstructedByDecorator(AbstractAuthenticatedRequestAwareDecorator):
	# TODO: This needs to go away in favor of the specific permission
	# when that role is hooked up

	def _course_from_context(self, context):
		return context

	def _predicate(self, context, result):
		# TODO: This can probably go back to using the AuthorizationPolicy methods
		# now that we're integrating the two
		return self._is_authenticated and  checkPermission(ACT_VIEW_REPORTS.id,
														   self._course_from_context(context))

def course_from_forum(forum):
	# If we are directly enclosed inside a course
	# (as we should be for non-legacy,) that's what
	# we want
	course = find_interface(forum, ICourseInstance)
	if course is not None:
		return course

	# otherwise, in the legacy case, we need to tweak
	# the community to get where we want to go
	board = forum.__parent__
	community = board.__parent__
	courses = ICourseAdministrativeLevel(community, None)
	if courses:
		# Assuming only one
		course = list(courses.values())[0]
		assert course.Discussions == board
		return course

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICourseInstanceEnrollment, IRequest)
class _StudentParticipationReport(_AbstractInstructedByDecorator):
	"""
	A link to return the student participation report.
	"""

	def _course_from_context(self, context):
		return ICourseInstance(context)

	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_STUDENT_PARTICIPATION,
							elements=(VIEW_STUDENT_PARTICIPATION,),
							title=_('Student Participation Report')) )

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICommunityForum, IRequest)
class _ForumParticipationReport(_AbstractInstructedByDecorator):
	"""
	A link to return the forum participation report.
	"""

	def _course_from_context(self, context):
		return course_from_forum(context)

	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_FORUM_PARTICIPATION,
							elements=(VIEW_FORUM_PARTICIPATION,),
							title=_('Forum Participation Report')) )

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICommunityHeadlineTopic, IRequest)
class _TopicParticipationReport(_AbstractInstructedByDecorator):
	"""
	A link to return the topic participation report.
	"""

	def _course_from_context(self, context):
		return course_from_forum(context.__parent__)

	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_TOPIC_PARTICIPATION,
							elements=(VIEW_TOPIC_PARTICIPATION,),
							title=_('Topic Participation Report')) )

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICourseInstance, IRequest)
class _CourseSummaryReport(_AbstractInstructedByDecorator):
	"""
	A link to return the course summary report.
	"""
	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_COURSE_SUMMARY,
							elements=(VIEW_COURSE_SUMMARY,),
							title=_('Course Summary Report')) )

def _find_course_for_user(data, user):
	if user is None:
		return None

	if ICourseCatalogEntry.providedBy(data):
		data = ICourseInstance(data)

	if ICourseInstance.providedBy(data):
		# Yay, they gave us one directly!
		course = data
	else:
		# Try to find the course within the context of the user;
		# this takes into account the user's enrollment status
		# to find the best course (sub) instance
		course = component.queryMultiAdapter( (data, user), ICourseInstance)

	if course is None:
		# Ok, can we get there genericlly, as in the old-school
		# fashion?
		course = ICourseInstance(data, None)
		if course is None:
			# Hmm, maybe we have an assignment-like object and we can
			# try to find the content package it came from and from there
			# go to the one-to-one mapping to courses we used to have
			course = ICourseInstance(find_interface(data, IContentPackage, strict=False),
									 None)
		if course is not None:
			# Snap. Well, we found a course (good!), but not by taking
			# the user into account (bad!)
			logger.debug("No enrollment for user %s in course %s found "
						 "for data %s; assuming generic/global course instance",
						 user, course, data)

	return course

@interface.implementer(IExternalMappingDecorator)
@component.adapter(IQAssignment, IRequest)
class _AssignmentSummaryReport(_AbstractInstructedByDecorator):
	"""
	A link to return the assignment summary report.
	"""
	def _course_from_context(self, context):
		self.course = find_interface(self.request.context, ICourseInstance,
									 strict=False)
		if self.course is None:
			self.course = _find_course_for_user(context, self.remoteUser)
		return self.course

	def _gradebook_entry( self, context ):
		book = IGradeBook( self.course )
		gradebook_entry = book.getColumnForAssignmentId( context.__name__ )
		return gradebook_entry

	def _do_decorate_external( self, context, result_map ):
		gradebook_entry = self._gradebook_entry( context )
		if gradebook_entry is None: # pragma: no cover
			# mostly tests
			return

		links = result_map.setdefault( LINKS, [] )
		links.append( Link( gradebook_entry,
							rel='report-%s' % VIEW_ASSIGNMENT_SUMMARY,
							elements=(VIEW_ASSIGNMENT_SUMMARY,),
							title=_('Assignment Summary Report')) )

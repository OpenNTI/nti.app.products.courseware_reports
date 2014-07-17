#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
$Id$
"""
from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import interface
from zope import component

from pyramid.interfaces import IRequest

from nti.externalization import interfaces as ext_interfaces
from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment

from nti.dataserver.contenttypes.forums.interfaces import ICommunityForum
from nti.dataserver.contenttypes.forums.interfaces import ICommunityHeadlineTopic

from nti.dataserver.traversal import find_interface

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseAdministrativeLevel

from nti.app.products.gradebook.interfaces import IGradeBookEntry

from nti.app.renderers.decorators import AbstractAuthenticatedRequestAwareDecorator

from . import MessageFactory as _
from . import VIEW_STUDENT_PARTICIPATION
from . import VIEW_FORUM_PARTICIPATION
from . import VIEW_TOPIC_PARTICIPATION
from . import VIEW_COURSE_SUMMARY
from . import VIEW_ASSIGNMENT_SUMMARY

from .interfaces import ACT_VIEW_REPORTS
from zope.security.management import checkPermission


LINKS = ext_interfaces.StandardExternalFields.LINKS
from nti.dataserver.links import Link


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

@interface.implementer(ext_interfaces.IExternalMappingDecorator)
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

@interface.implementer(ext_interfaces.IExternalMappingDecorator)
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

@interface.implementer(ext_interfaces.IExternalMappingDecorator)
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

@interface.implementer(ext_interfaces.IExternalMappingDecorator)
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

@interface.implementer(ext_interfaces.IExternalMappingDecorator)
@component.adapter(IGradeBookEntry, IRequest)
class _AssignmentSummaryReport(_AbstractInstructedByDecorator):
	"""
	A link to return the assignment summary report.
	"""
	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_ASSIGNMENT_SUMMARY,
							elements=(VIEW_ASSIGNMENT_SUMMARY,),
							title=_('Assignment Summary Report')) )

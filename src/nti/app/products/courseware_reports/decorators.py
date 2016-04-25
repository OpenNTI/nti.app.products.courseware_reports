#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from . import MessageFactory as _

from zope import component
from zope import interface

from zope.security.management import checkPermission

from pyramid.interfaces import IRequest

from nti.app.assessment.common import inquiry_submissions

from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment

from nti.app.products.gradebook.interfaces import IGradeBook

from nti.app.renderers.decorators import AbstractAuthenticatedRequestAwareDecorator

from nti.assessment.interfaces import IQInquiry
from nti.assessment.interfaces import IQAssignment

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.contenttypes.presentation.interfaces import INTIInquiryRef

from nti.dataserver.contenttypes.forums.interfaces import ICommunityForum
from nti.dataserver.contenttypes.forums.interfaces import ICommunityHeadlineTopic

from nti.externalization.interfaces import StandardExternalFields
from nti.externalization.interfaces import IExternalMappingDecorator

from nti.links.links import Link

from nti.traversal.traversal import find_interface

from nti.app.products.courseware_reports import VIEW_COURSE_SUMMARY
from nti.app.products.courseware_reports import VIEW_INQUIRY_REPORT
from nti.app.products.courseware_reports import VIEW_ASSIGNMENT_SUMMARY
from nti.app.products.courseware_reports import VIEW_FORUM_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_TOPIC_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_STUDENT_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_SELF_ASSESSMENT_SUMMARY

from nti.app.products.courseware_reports.interfaces import ACT_VIEW_REPORTS

from nti.app.products.courseware_reports.utils import course_from_forum
from nti.app.products.courseware_reports.utils import find_course_for_user

LINKS = StandardExternalFields.LINKS

class _AbstractInstructedByDecorator(AbstractAuthenticatedRequestAwareDecorator):

	def _course_from_context(self, context):
		return context

	def _predicate(self, context, result):
		# TODO: This can probably go back to using the AuthorizationPolicy methods
		# now that we're integrating the two
		# XXX: Surprisingly, our has_permission check fails because we turn the course
		# into an ACLProvider when we check zope permissions (the fall-back).
		return 	self._is_authenticated \
			and checkPermission(ACT_VIEW_REPORTS.id,
								self._course_from_context( context ))

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICourseInstanceEnrollment, IRequest)
class _StudentParticipationReport(_AbstractInstructedByDecorator):
	"""
	A link to return the student participation report.
	"""

	def _course_from_context(self, context):
		return ICourseInstance(context)

	def _do_decorate_external(self, context, result_map):
		links = result_map.setdefault(LINKS, [])
		links.append(Link(context,
						  rel='report-%s' % VIEW_STUDENT_PARTICIPATION,
						  elements=(VIEW_STUDENT_PARTICIPATION,),
						  title=_('Student Participation Report')))

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICommunityForum, IRequest)
class _ForumParticipationReport(_AbstractInstructedByDecorator):
	"""
	A link to return the forum participation report.
	"""

	def _predicate(self, context, result):
		result = super( _ForumParticipationReport, self )._predicate( context, result )
		if result:
			# Decorate if we have any comments in this forum's topics.
			result = any( len(x.values()) for x in context.values() )
		return result and len( context )

	def _course_from_context(self, context):
		return course_from_forum(context)

	def _do_decorate_external(self, context, result_map):
		links = result_map.setdefault(LINKS, [])
		links.append(Link(context,
						  rel='report-%s' % VIEW_FORUM_PARTICIPATION,
						  elements=(VIEW_FORUM_PARTICIPATION,),
						  title=_('Forum Participation Report')))

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICommunityHeadlineTopic, IRequest)
class _TopicParticipationReport(_AbstractInstructedByDecorator):
	"""
	A link to return the topic participation report.
	"""

	def _predicate(self, context, result):
		result = super( _TopicParticipationReport, self )._predicate( context, result )
		return result and len( context.values() )

	def _course_from_context(self, context):
		return course_from_forum(context.__parent__)

	def _do_decorate_external(self, context, result_map):
		links = result_map.setdefault(LINKS, [])
		links.append(Link(context,
						  rel='report-%s' % VIEW_TOPIC_PARTICIPATION,
						  elements=(VIEW_TOPIC_PARTICIPATION,),
						  title=_('Topic Participation Report')))

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICourseInstance, IRequest)
class _CourseSummaryReport(_AbstractInstructedByDecorator):
	"""
	A link to return the course summary report.
	"""

	def _do_decorate_external(self, context, result_map):
		links = result_map.setdefault(LINKS, [])
		links.append(Link(context,
						  rel='report-%s' % VIEW_COURSE_SUMMARY,
						  elements=(VIEW_COURSE_SUMMARY,),
						  title=_('Course Summary Report')))

@interface.implementer(IExternalMappingDecorator)
@component.adapter(ICourseInstance, IRequest)
class _SelfAssessmentSummaryReport(_AbstractInstructedByDecorator):
	"""
	A link to return the self-assessment summary report.
	"""

	def _do_decorate_external(self, context, result_map):
		links = result_map.setdefault(LINKS, [])
		links.append(Link(context,
						  rel='report-%s' % VIEW_SELF_ASSESSMENT_SUMMARY,
						  elements=(VIEW_SELF_ASSESSMENT_SUMMARY,),
						  title=_('SelfAssessment Summary Report')))

@interface.implementer(IExternalMappingDecorator)
@component.adapter(IQAssignment, IRequest)
class _AssignmentSummaryReport(_AbstractInstructedByDecorator):
	"""
	A link to return the assignment summary report.
	"""

	def _predicate(self, context, result):
		result = super( _AssignmentSummaryReport, self )._predicate( context, result )
		if result:
			gradebook_entry = self._gradebook_entry(context)
			if gradebook_entry is not None:
				result = len( gradebook_entry.items() )
		return result

	def _course_from_context(self, context):
		self.course = find_interface(self.request.context, ICourseInstance,
									 strict=False)
		if self.course is None:
			self.course = find_course_for_user(context, self.remoteUser)
		return self.course

	def _gradebook_entry(self, context):
		book = IGradeBook(self.course)
		gradebook_entry = book.getColumnForAssignmentId(context.__name__)
		return gradebook_entry

	def _do_decorate_external(self, context, result_map):
		gradebook_entry = self._gradebook_entry(context)
		if gradebook_entry is None:  # pragma: no cover
			# mostly tests
			return

		links = result_map.setdefault(LINKS, [])
		links.append(Link(gradebook_entry,
						  rel='report-%s' % VIEW_ASSIGNMENT_SUMMARY,
						  elements=(VIEW_ASSIGNMENT_SUMMARY,),
						  title=_('Assignment Summary Report')))

@interface.implementer(IExternalMappingDecorator)
@component.adapter(IQInquiry, IRequest)
@component.adapter(INTIInquiryRef, IRequest)
class _InquiryReport(_AbstractInstructedByDecorator):
	"""
	A link to return the inquiry report.
	"""

	def _predicate(self, context, result):
		result = super( _InquiryReport, self )._predicate( context, result )
		if result:
			course = self._course_from_context( context )
			# XXX: Subinstances?
			result = inquiry_submissions( context, course, subinstances=False )
			result = len( result )
		return result

	def _course_from_context(self, context):
		inquiry = IQInquiry(context, None)
		self.course = find_interface(inquiry, ICourseInstance, strict=False)
		if self.course is None:
			self.course = find_course_for_user(inquiry, self.remoteUser)
		return self.course

	def _do_decorate_external(self, context, result_map):
		inquiry = IQInquiry(context, None)
		if inquiry is not None:
			links = result_map.setdefault(LINKS, [])
			links.append(Link(context,
							  rel='report-%s' % VIEW_INQUIRY_REPORT,
							  elements=(VIEW_INQUIRY_REPORT,),
							  title=_('Inquiry Report')))

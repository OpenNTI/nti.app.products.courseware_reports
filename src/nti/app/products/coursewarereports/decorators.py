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

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.app.products.gradebook.interfaces import IGradeBookEntry

from nti.app.renderers.decorators import AbstractAuthenticatedRequestAwareDecorator

from . import MessageFactory as _
from . import VIEW_STUDENT_PARTICIPATION
from . import VIEW_FORUM_PARTICIPATION
from . import VIEW_TOPIC_PARTICIPATION
from . import VIEW_COURSE_SUMMARY
from . import VIEW_ASSIGNMENT_SUMMARY

LINKS = ext_interfaces.StandardExternalFields.LINKS
from nti.dataserver.links import Link

@interface.implementer(ext_interfaces.IExternalMappingDecorator)
@component.adapter(ICourseInstanceEnrollment, IRequest)
class _StudentParticipationReport(AbstractAuthenticatedRequestAwareDecorator):
	"""
	A link to return the student participation report.
	"""
	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_STUDENT_PARTICIPATION,
							elements=(VIEW_STUDENT_PARTICIPATION,),
							title=_('Student Participation Report')) )	
		
@interface.implementer(ext_interfaces.IExternalMappingDecorator)
@component.adapter(ICommunityForum, IRequest)
class _ForumParticipationReport(AbstractAuthenticatedRequestAwareDecorator):
	"""
	A link to return the forum participation report.
	"""
	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_FORUM_PARTICIPATION,
							elements=(VIEW_FORUM_PARTICIPATION,),
							title=_('Forum Participation Report')) )
		
@interface.implementer(ext_interfaces.IExternalMappingDecorator)
@component.adapter(ICommunityHeadlineTopic, IRequest)
class _TopicParticipationReport(AbstractAuthenticatedRequestAwareDecorator):
	"""
	A link to return the topic participation report.
	"""
	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_TOPIC_PARTICIPATION,
							elements=(VIEW_TOPIC_PARTICIPATION,),
							title=_('Topic Participation Report')) )	
		
@interface.implementer(ext_interfaces.IExternalMappingDecorator)
@component.adapter(ICourseInstance, IRequest)
class _CourseSummaryReport(AbstractAuthenticatedRequestAwareDecorator):
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
class _AssignmentSummaryReport(AbstractAuthenticatedRequestAwareDecorator):
	"""
	A link to return the assignment summary report.
	"""
	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-%s' % VIEW_ASSIGNMENT_SUMMARY,
							elements=(VIEW_ASSIGNMENT_SUMMARY,),
							title=_('Assignment Summary Report')) )									
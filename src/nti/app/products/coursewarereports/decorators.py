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

from nti.app.renderers.decorators import AbstractAuthenticatedRequestAwareDecorator

from . import MessageFactory as _
from . import VIEW_STUDENT_PARTICIPATION

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
		
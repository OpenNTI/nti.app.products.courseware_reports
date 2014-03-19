#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
$Id$
"""
from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import interface

from nti.externalization import interfaces as ext_interfaces

from nti.app.renderers.decorators import AbstractAuthenticatedRequestAwareDecorator

from . import MessageFactory as _

LINKS = ext_interfaces.StandardExternalFields.LINKS
from nti.dataserver.links import Link

@interface.implementer(ext_interfaces.IExternalMappingDecorator)
class _StudentParticipationReport(AbstractAuthenticatedRequestAwareDecorator):
	"""
	A link to return the student participation report.
	"""
	def _do_decorate_external( self, context, result_map ):
		links = result_map.setdefault( LINKS, [] )
		links.append( Link( context,
							rel='report-StudentParticipationReport.pdf',
							elements=('StudentParticipationReport.pdf',),
							title=_('Student Participation Report')) )	
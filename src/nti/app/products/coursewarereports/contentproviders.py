#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RML content providers.

.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import interface

from zope.contentprovider.interfaces import IContentProvider
from zope.contentprovider.provider import ContentProviderBase

class DummyContentProvider(ContentProviderBase):

	def render(self, *args, **kwargs):
		return "<tr><td/></tr>"

@interface.implementer(IContentProvider)
class StudentInfoContentProvider(ContentProviderBase):
	# XXX maybe this should be a macro? Unless we can get
	# all the way to zope.viewlet and/or z3c.layout
	# using zope.viewlet.SimpleViewletClass should let us
	# use templates
	def render(self, *args, **kwargs):
		rows = []
		# No need to escape Username, we don't allow invalid
		# characters
		rows.append( '<tr><td>Username</td><td>%s</td></tr>' % self.context.Username)

		return '\n'.join(rows)

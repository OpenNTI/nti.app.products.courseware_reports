#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""


.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import interface

from zope.viewlet.interfaces import IViewletManager

from zope.security.permission import Permission

# Until we have true pluggable auth-folders that we traverse through
# we might add instructors to a role having this permission using
# traversal events
ACT_VIEW_REPORTS = Permission('nti.actions.coursewarereports.view_reports')


class IPDFReportView(interface.Interface):
	"""
	A marker interface that all the reporting views
	that generate PDFs and work from the same set
	of PDF templates are expected to implement.

	In this way, we have a distinct way of registering :mod:`z3c.macro``
	definitions.
	"""

class IPDFReportHeaderManager(IViewletManager):
	"""
	Viewlet manager for the headers of pdf reports.
	"""

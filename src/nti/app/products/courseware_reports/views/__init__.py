#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from .. import MessageFactory as _

import six
import time
import isodate
from datetime import date
from datetime import datetime

from zope import interface

from zope.container.contained import  Contained

from zope.location.interfaces import IContained

from zope.traversing.interfaces import IPathAdapter

ALL_USERS = 'ALL_USERS'

CHART_COLORS = ['#1abc9c', '#3498db', '#3f5770', '#e74c3c', '#af7ac4', '#f1c40f',
				'#e67e22', '#bcd3c7', '#16a085', '#e364ae', '#c0392b', '#2980b9',
				'#8e44ad' ]

FORUM_OBJECT_MIMETYPES = ['application/vnd.nextthought.forums.generalforumcomment',
						  'application/vnd.nextthought.forums.communityforumcomment',
						  'application/vnd.nextthought.forums.communitytopic',
						  'application/vnd.nextthought.forums.communityheadlinetopic']

ENGAGEMENT_OBJECT_MIMETYPES = ['application/vnd.nextthought.note',
							   'application/vnd.nextthought.highlight']

# XXX: Fix a unicode decode issue.
# TODO: Make this a formal patch
import reportlab.platypus.paragraph
class _SplitText(unicode):
	pass
reportlab.platypus.paragraph._SplitText = _SplitText

@interface.implementer(IPathAdapter, IContained)
class ReportAdapter(Contained):

	__name__ = 'reports'

	def __init__(self, context, request):
		self.context = context
		self.request = request
		self.__parent__ = context

def is_valid_timestamp(ts):
	try:
		ts = float(ts)
		return ts >= 0
	except (TypeError, ValueError):
		return False

def parse_datetime(t, safe=False):
	try:
		result = t
		if t is None:
			result = None
		elif is_valid_timestamp(t):
			result = float(t)
		elif isinstance(t, six.string_types):
			try:
				result = isodate.parse_datetime(t)
			except Exception:
				result = isodate.parse_date(t)
			result = time.mktime(result.timetuple())
		elif isinstance(t, (date, datetime)):
			result = time.mktime(t.timetuple())
		return result
	except Exception as e:
		if safe:
			return None
		raise e

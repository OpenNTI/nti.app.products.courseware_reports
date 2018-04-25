#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import six
import time
import isodate

from datetime import date
from datetime import datetime

from zope import interface

from zope.container.contained import  Contained

from zope.location.interfaces import IContained

from zope.traversing.interfaces import IPathAdapter

from nti.app.products.courseware_reports import MessageFactory as _

logger = __import__('logging').getLogger(__name__)

ALL_USERS = 'ALL_USERS'

CHART_COLORS = [u'#1abc9c', u'#3498db', u'#3f5770', u'#e74c3c', u'#af7ac4', u'#f1c40f',
				u'#e67e22', u'#bcd3c7', u'#16a085', u'#e364ae', u'#c0392b', u'#2980b9',
				u'#8e44ad' ]

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

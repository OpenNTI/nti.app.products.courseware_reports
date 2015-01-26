#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import six
import time
import isodate
from datetime import date
from datetime import datetime

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
		elif isinstance(t, (date,datetime)):
			result = time.mktime(t.timetuple())
		return result
	except Exception as e:
		if safe:
			return None
		raise e

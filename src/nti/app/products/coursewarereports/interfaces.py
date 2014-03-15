#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""


.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)


from zope.security.permission import Permission

# Until we have true pluggable auth-folders that we traverse through
# we might add instructors to a role having this permission using
# traversal events
ACT_VIEW_REPORTS = Permission('nti.actions.coursewarereports.view_reports')

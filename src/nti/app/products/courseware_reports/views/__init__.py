#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from .. import MessageFactory as _

from .. import VIEW_VIDEO_REPORT
from .. import VIEW_COURSE_SUMMARY
from .. import VIEW_ASSIGNMENT_SUMMARY
from .. import VIEW_TOPIC_PARTICIPATION
from .. import VIEW_FORUM_PARTICIPATION
from .. import VIEW_STUDENT_PARTICIPATION

from ..interfaces import IPDFReportView
from ..interfaces import ACT_VIEW_REPORTS

from ..reports import _AnswerStat
from ..reports import _TopCreators
from ..reports import _common_buckets
from ..reports import _CommonBuckets
from ..reports import _build_buckets_options
from ..reports import _get_self_assessments_for_course
from ..reports import _adjust_timestamp
from ..reports import _adjust_date
from ..reports import _format_datetime
from ..reports import _assignment_stat_for_column
from ..reports import _build_question_stats
from ..reports import _QuestionPartStat
from ..reports import _QuestionStat
from ..reports import _DateCategoryAccum
from ..reports import _do_get_containers_in_course

import textwrap
import BTrees

from zope import component
from zope import interface

from lxml import html

from six import string_types
from numbers import Number

from docutils.utils import roman

from numpy import percentile

from collections import namedtuple, OrderedDict
from collections import defaultdict

from datetime import timedelta
from datetime import datetime

from itertools import chain

from pyramid.view import view_config
from pyramid.view import view_defaults
from pyramid.traversal import find_interface

from z3c.pagelet.browser import BrowserPagelet

from zope.catalog.interfaces import ICatalog
from zope.catalog.catalog import ResultSet

from zope.intid.interfaces import IIntIds
from zope.traversing.interfaces import IPathAdapter
from zope.location.interfaces import IContained
from zope.container import contained as zcontained
from zope.security.management import checkPermission

from nti.common.property import Lazy

from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.app.assessment.interfaces import IUsersCourseAssignmentHistory

from nti.assessment.common import grader_for_response

from nti.assessment.interfaces import IQAssignment
from nti.assessment.interfaces import IQAssignmentDateContext

from nti.assessment.randomized.interfaces import IQRandomizedPart

from nti.app.products.courseware.interfaces import IVideoUsageStats
from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment

from nti.app.products.gradebook.interfaces import IGrade
from nti.app.products.gradebook.interfaces import IGradeBook
from nti.app.products.gradebook.interfaces import IGradeBookEntry
from nti.app.products.gradebook.assignments import get_course_assignments

from nti.contenttypes.courses.interfaces import ICourseCatalogEntry
from nti.contenttypes.courses.interfaces import	ICourseSubInstance
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseAssessmentItemCatalog

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import IDeletedObjectPlaceholder
from nti.dataserver.interfaces import IUsernameSubstitutionPolicy
from nti.dataserver.interfaces import IEnumerableEntityContainer

from nti.dataserver.users.interfaces import IFriendlyNamed
from nti.dataserver.users.users import User
from nti.dataserver.users.entity import Entity

from nti.dataserver.contenttypes.forums.interfaces import ICommunityBoard
from nti.dataserver.contenttypes.forums.interfaces import ICommunityForum
from nti.dataserver.contenttypes.forums.interfaces import ICommunityHeadlineTopic
from nti.dataserver.contenttypes.forums.interfaces import ITopic
from nti.dataserver.contenttypes.forums.interfaces import IGeneralForumComment

from nti.dataserver.metadata_index import CATALOG_NAME

from nti.dataserver.authorization import ACT_READ
from nti.dataserver.authorization import ACT_MODERATE

CHART_COLORS = ['#1abc9c', '#3498db', '#3f5770', '#e74c3c', '#af7ac4', '#f1c40f', '#e67e22', '#bcd3c7', '#16a085', '#e364ae', '#c0392b', '#2980b9', '#8e44ad' ]

# XXX: Fix a unicode decode issue.
# TODO: Make this a formal patch
import reportlab.platypus.paragraph
class _SplitText(unicode):
	pass
reportlab.platypus.paragraph._SplitText = _SplitText

ALL_USERS = 'ALL_USERS'

FORUM_OBJECT_MIMETYPES = ['application/vnd.nextthought.forums.generalforumcomment',
						  'application/vnd.nextthought.forums.communityforumcomment',
						  'application/vnd.nextthought.forums.communitytopic',
						  'application/vnd.nextthought.forums.communityheadlinetopic']

ENGAGEMENT_OBJECT_MIMETYPES = ['application/vnd.nextthought.note',
							   'application/vnd.nextthought.highlight']


@interface.implementer(IPathAdapter, IContained)
class ReportAdapter(zcontained.Contained):

	__name__ = 'reports'

	def __init__(self, context, request):
		self.context = context
		self.request = request
		self.__parent__ = context

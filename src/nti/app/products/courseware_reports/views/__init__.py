#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from .. import MessageFactory as _

from .. import VIEW_COURSE_SUMMARY
from .. import VIEW_ASSIGNMENT_SUMMARY
from .. import VIEW_TOPIC_PARTICIPATION
from .. import VIEW_FORUM_PARTICIPATION
from .. import VIEW_STUDENT_PARTICIPATION
from .. import VIEW_VIDEO_REPORT

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

FORUM_OBJECT_MIMETYPES = ['application/vnd.nextthought.forums.generalforumcomment',
						  'application/vnd.nextthought.forums.communityforumcomment',
						  'application/vnd.nextthought.forums.communitytopic',
						  'application/vnd.nextthought.forums.communityheadlinetopic']

ENGAGEMENT_OBJECT_MIMETYPES = ['application/vnd.nextthought.note',
							   'application/vnd.nextthought.highlight']

class _StudentInfo( namedtuple( '_StudentInfo',
								('display', 'username', 'count', 'perc' ))):
	"""Holds general student info. 'count' and 'perc' are optional values"""
	def __new__( cls, display, username, count=None, perc=None ):
		return super(_StudentInfo,cls).__new__( cls, display, username, count, perc )

ALL_USERS = 'ALL_USERS'

def _get_enrollment_scope_dict( course, instructors=set() ):
	"Build a dict of scope_name to usernames."
	# XXX We are not exposing these multiple scopes in many places,
	# including many reports and in TopCreators.
	# XXX This is confusing if we are nesting scopes.  Perhaps
	# it makes more sense to keep things in the Credit/NonCredit camps.
	# Seems like it would make sense to have an Everyone scope...
	# { Everyone: { Public : ( Open, Purchased ), ForCredit : ( FCD, FCND ) }}
	results = {}
	# Lumping purchased in with public.
	public_scope = course.SharingScopes.get( 'Public', None )
	purchased_scope = course.SharingScopes.get( 'Purchased', None )
	non_public_users = set()
	for scope_name in course.SharingScopes:
		scope = course.SharingScopes.get( scope_name, None )

		if 		scope is not None \
			and scope not in (public_scope, purchased_scope):

			# If our scope is not 'public'-ish, store it separately.
			# All credit-type users should end up in ForCredit.
			scope_users = {x.lower() for x in IEnumerableEntityContainer(scope).iter_usernames()}
			scope_users = scope_users - instructors
			results[scope_name] = scope_users
			non_public_users = non_public_users.union( scope_users )

	all_users = {x.lower() for x in IEnumerableEntityContainer(public_scope).iter_usernames()}
	results['Public'] = all_users - non_public_users - instructors
	results[ALL_USERS] = all_users
	return results

from pyramid.httpexceptions import HTTPForbidden

@view_defaults(route_name='objects.generic.traversal',
			   renderer="../templates/std_report_layout.rml",
			   request_method='GET',
			   permission=ACT_READ)
@interface.implementer(IPDFReportView)
class _AbstractReportView(AbstractAuthenticatedView,
						  BrowserPagelet):

	family = BTrees.family64

	def __init__(self, context, request):
		self.options = {}
		# Our two parents take different arguments
		AbstractAuthenticatedView.__init__(self, request)
		BrowserPagelet.__init__(self, context, request)

		if request.view_name:
			self.filename = request.view_name

	def _check_access(self):
		if not checkPermission(ACT_VIEW_REPORTS.id, self.course):
			raise HTTPForbidden()

	@Lazy
	def course(self):
		return ICourseInstance(self.context)

	@Lazy
	def course_start_date(self):
		try:
			# legacy code path, but faster
			entry = self.course.legacy_catalog_entry
		except AttributeError:
			entry = ICourseCatalogEntry(self.course)

		return entry.StartDate

	@Lazy
	def md_catalog(self):
		return component.getUtility(ICatalog,CATALOG_NAME)
	@Lazy
	def uidutil(self):
		return component.getUtility(IIntIds)

	@Lazy
	def intids_created_by_students(self):
		return self.md_catalog['creator'].apply({'any_of': self.all_student_usernames})

	@Lazy
	def intids_created_by_everyone(self):
		return self.md_catalog['creator'].apply({'any_of': self.all_usernames})

	#Making all of these include lowercase names
	@Lazy
	def instructor_usernames(self):
		return {x.id.lower() for x in self.course.instructors}

	@Lazy
	def _get_enrollment_scope_dict(self):
		"Build a dict of scope_name to usernames."
		# XXX We are not exposing these multiple scopes in many places,
		# including many reports and in TopCreators.
		# XXX This is confusing if we are nesting scopes.  Perhaps
		# it makes more sense to keep things in the Credit/NonCredit camps.
		return _get_enrollment_scope_dict( self.course, self.instructor_usernames )

	def _get_users_for_scope(self, scope_name):
		"Returns a set of users for the given scope_name, or None if that scope does not exist."
		scope_dict = self._get_enrollment_scope_dict
		return scope_dict[scope_name]

	@Lazy
	def for_credit_student_usernames(self):
		return self._get_users_for_scope( 'ForCredit' )

	@Lazy
	def open_student_usernames(self):
		return self.all_student_usernames - self.for_credit_student_usernames

	@Lazy
	def all_student_usernames(self):
		return self.all_usernames - self.instructor_usernames

	@Lazy
	def all_usernames(self):
		return self._get_users_for_scope( ALL_USERS )

	@Lazy
	def count_all_students(self):
		return len(self.all_student_usernames)
	@Lazy
	def count_credit_students(self):
		return len(self.for_credit_student_usernames)

	@Lazy
	def count_non_credit_students(self):
		return len(self.open_student_usernames)

	@Lazy
	def all_user_intids(self):
		ids = self.family.II.TreeSet()
		ids.update( IEnumerableEntityContainer(self.course.SharingScopes['Public']).iter_intids() )
		return ids

	def get_student_info(self, username ):
		"""Given a username, return a _StudentInfo tuple"""
		# Actually, the `creator` field is meant to hold an arbitrary
		# entity. If it is a user, User.get_user simply returns it.
		# If it's some other entity object, default to 'System'.
		try:
			user = User.get_user( username )
		except TypeError:
			user = None
			username = 'System'
		if user:
			return self.build_user_info( user )
		return _StudentInfo( username, username )

	def _replace_username(self, username):
		policy = component.queryUtility( IUsernameSubstitutionPolicy )
		result = policy.replace( username ) if policy else username
		return result

	def build_user_info(self, user):
		"""Given a user, return a _StudentInfo tuple"""
		named_user = IFriendlyNamed( user )
		display_name = named_user.alias or named_user.realname or named_user.username

		username = ""
		# Do not display username of open students
		if user.username.lower() in self.for_credit_student_usernames:
			username = self._replace_username( user.username )

		return _StudentInfo( display_name, username )

	def filter_objects(self,objects):
		"""Returns a set of filtered objects"""
		return [ x for x in objects
				if not IDeletedObjectPlaceholder.providedBy( x ) ]

	def course_name(self):
		catalog_entry = ICourseCatalogEntry( self.course, None )
		result = catalog_entry.ProviderUniqueID if catalog_entry else self.course.__name__
		return result

	def generate_footer( self ):
		date = _adjust_date( datetime.utcnow() )
		date = date.strftime( '%b %d, %Y %I:%M %p' )
		title = self.report_title
		course = self.course_name()
		student = getattr( self, 'student_user', '' )
		return "%s %s %s %s" % ( title, course, student, date )

	def generate_semester( self ):
		start_date = self.course_start_date
		start_month = start_date.month if start_date else None
		if start_month < 5:
			semester = _( 'Spring' )
		elif start_month < 8:
			semester = _( 'Summer' )
		else:
			semester = _( 'Fall' )

		start_year = start_date.year if start_date else None
		return '%s %s' % ( semester, start_year ) if start_date else ''

	def wrap_text( self, text, size ):
		return textwrap.fill( text, size )

class _AssignmentInfo(object):

	def __init__(self,title,submitted,submitted_late,grade_value,history,due_date):
		self.title = title
		self.submitted = submitted
		self.submitted_late = submitted_late
		self.grade_value = grade_value
		self.history = history
		self.due_date = due_date

@view_config(context=ICourseInstanceEnrollment,
			 name=VIEW_STUDENT_PARTICIPATION)
class StudentParticipationReportPdf(_AbstractReportView):

	report_title = _('Student Participation Report')

	TopicCreated = namedtuple('TopicCreated',
							  ('topic', 'topic_name', 'forum_name', 'created'))

	@Lazy
	def student_user(self):
		return IUser(self.context)

	@Lazy
	def intids_created_by_student(self):
		return self.md_catalog['creator'].apply({'any_of': (self.context.Username,)})

	def _build_user_info(self,options):
		options['user'] = self.build_user_info( self.student_user )

	def _build_forum_data(self, options):
		course = self.course
		md_catalog = self.md_catalog
		uidutil = self.uidutil

		if ICourseSubInstance.providedBy( course ):
			course_boards = ( course.Discussions, course.__parent__.__parent__.Discussions )
		else:
			course_boards = (course.Discussions,)
		# Graph of forum participation over time (time-series of forum-related
		# objects created bucketed by something--day/week?) probably a linePlot?
		# We find these objects using the catalog rather than traversing through
		# all possible forums/topics of the course on the theory that the total
		# number of objects the user created is going to be smaller than
		# all the objects in the course discussion board. This could be further improved
		# by applying a time limit to the objects the user created.
		intids_created_by_student = self.intids_created_by_student
		intids_of_forum_objects = md_catalog['mimeType'].apply({'any_of': FORUM_OBJECT_MIMETYPES})
		# We could apply based on createdTime to be no less than the start time of the
		# course
		intids_of_forum_objects_created_by_student = md_catalog.family.IF.intersection(intids_created_by_student, intids_of_forum_objects)
		forum_objects_created_by_student = ResultSet(intids_of_forum_objects_created_by_student,
													 uidutil )

		#Grab by course, ignore deleted comments and those before course start
		live_objects = self.filter_objects( (	x for x in forum_objects_created_by_student
												if find_interface(x, ICommunityBoard) in course_boards) )

		# Group the forum objects by day and week
		time_buckets = _common_buckets(	live_objects,
										self,
										self.course_start_date )

		# Tabular breakdown of what topics the user created in what forum
		# and how many comments in which topics (could be bulkData or actual blockTable)
		topics_created = []
		comment_count_by_topic = defaultdict(int)
		for x in live_objects:
			if ITopic.providedBy(x):
				info = self.TopicCreated( x, x.title, x.__parent__.title, x.created )
				topics_created.append(info)
			elif IGeneralForumComment.providedBy(x):
				comment_count_by_topic[x.__parent__] += 1

		topics_created.sort(key=lambda x: (x.forum_name, x.topic_name))
		options['topics_created'] = topics_created
		options['total_forum_objects_created'] = len(live_objects)
		options['comment_count_by_topic'] = sorted(comment_count_by_topic.items(),
												   key=lambda x: (x[0].__parent__.title, x[0].title))
		stat = _build_buckets_options(options, time_buckets)
		options['student_forum_participation'] = stat

	def _build_self_assessment_data(self, options):
		md_catalog = self.md_catalog
		self_assessments = _get_self_assessments_for_course(self.course)
		self_assessment_qsids = {x.ntiid: x for x in self_assessments}
		# We can find the self-assessments the student submitted in a few ways
		# one would be to look at the user's contained data for each containerID
		# of the self assessment and see if there is an IQAssessedQuestionSet.
		# Another would be to find all IQAssessedQuestionSets the user has completed
		# using the catalog and match them up by IDs. This might be slightly slower, but it
		# has the advantage of not knowing anything about storage.
		intids_of_submitted_qsets = md_catalog['mimeType'].apply({'any_of': ('application/vnd.nextthought.assessment.assessedquestionset',)})
		intids_of_submitted_qsets_by_student = md_catalog.family.IF.intersection( intids_of_submitted_qsets,
																				  self.intids_created_by_student )
		# We could further filter this by containerId, based on the
		# assumption that The qs's __parent__ is always the 'home'
		# content unit and that the UI always posts things to be contained there.
		# However, we're working with (probably) a small set of objects, so to
		# avoid more assumptions we directly check qs IDs
		qsets_by_student_in_course = [x for x in ResultSet(intids_of_submitted_qsets_by_student, self.uidutil)
									  if x.questionSetId in self_assessment_qsids]

		title_to_count = dict()
		# XXX: The title might not be right, the UI I think is doing something
		# more involved
		def _title_of_qs(qs):
			if qs.title:
				return qs.title
			return qs.__parent__.title
		for asm in self_assessments:
			title_to_count[_title_of_qs(asm)] = 0
		for submission in qsets_by_student_in_course:
			asm = self_assessment_qsids[submission.questionSetId]
			title_to_count[_title_of_qs(asm)] += 1

		options['self_assessment_title_to_count'] = sorted(title_to_count.items())

	def _build_assignment_data(self, options):
		assignment_catalog = get_course_assignments( self.course )
		histories = component.getMultiAdapter((self.course, self.student_user),
											  IUsersCourseAssignmentHistory)

		asg_data = list()
		date_context = IQAssignmentDateContext( self.course )

		for assignment in assignment_catalog:
			history_item = histories.get(assignment.ntiid)
			if history_item:
				grade_value = getattr(IGrade(history_item, None), 'value', '')
				# Convert the webapp's "number - letter" scheme to a number, iff
				# the letter scheme is empty
				if grade_value and isinstance(grade_value, string_types) and grade_value.endswith(' -'):
					try:
						grade_value = float(grade_value.split()[0])
					except ValueError:
						pass
				if isinstance(grade_value, Number):
					grade_value = '%0.1f' % grade_value
				submitted = history_item.created
			else:
				grade_value = ''
				submitted = ''
			due_date = date_context.of( assignment ).available_for_submission_ending
			submitted_late = submitted > due_date if due_date and submitted else False

			asg_data.append(_AssignmentInfo(assignment.title, submitted,
											submitted_late,
											grade_value, history_item,
											due_date) )

		#Sort null due_dates to end of result
		asg_data.sort(key=lambda x: (x.due_date is None, x.due_date, x.title))
		#Toggle timezones
		for x in asg_data:
			if x.due_date:
				x.due_date = _format_datetime( _adjust_date( x.due_date ) )
			if x.submitted:
				x.submitted = _format_datetime( _adjust_date( x.submitted ) )
		options['assignments'] = asg_data


	def __call__(self):
		"""
		Return the `options` dictionary for formatting. The dictionary
		will have the following keys:

		assignments
			A list, sorted by assignment title containing objects with the attributes
			`title`, `submitted` (a datetime) and `grade_value`.

		self_assessment_title_to_count
			A list of tuples (title, count) giving the number of times each self-assessment
			was taken, sorted by title.

		topics_created
			A list of objects with the keys `topic`, `topic_name`, `forum_name`, `created`
			giving all the topics the user created. Sorted by forum name and topic name.

		total_forum_objects_created
			An integer.

		comment_count_by_topic
			A list of tuples (topic, count) giving the number of comments the user
			created. Sorted by forum name and topic name.

		student_forum_participation
			A :class:`ForumObjectsStat`

		"""
		self._check_access()
		# Collect data and return it in a form to be rendered
		# (a dictionary containing data and callable objects)
		options = self.options
		self._build_user_info(options)

		self._build_forum_data(options)

		# Each self-assessment and how many times taken (again bulkData)
		self._build_self_assessment_data(options)

		# Table of assignment history and grades for all assignments in course
		self._build_assignment_data(options)

		self.options = options
		return options


from ..decorators import course_from_forum

@view_config(context=ICommunityForum,
			 name=VIEW_FORUM_PARTICIPATION)
class ForumParticipationReportPdf(_AbstractReportView):

	report_title = _('Forum Participation Report')

	agg_creators = None

	TopicStats = namedtuple('TopicStats',
							('title', 'creator', 'created',
							'comment_count', 'distinct_user_count'))

	UserStats = namedtuple('UserStats',
						   ('username', 'topics_created',
						'total_comment_count', 'instructor_reply_count'))

	def _course_from_forum(self, forum):
		return course_from_forum(forum)

	@property
	def course(self):
		return self._course_from_forum(self.context)

	def _build_top_commenters(self, options):

		def _all_comments():
			for topic in self.context.values():
				# Should we use filter objects?
				for comment in topic.values():
					if not IDeletedObjectPlaceholder.providedBy( comment ):
						yield comment
		buckets = _common_buckets(	_all_comments(),
									self,
									self.course_start_date,
									self.agg_creators)
		options['group_dates'] = buckets.group_dates
		options['top_commenters'] = buckets.top_creators
		options['top_commenters_colors'] = CHART_COLORS

		all_forum_stat = _build_buckets_options(options, buckets)
		options['all_forum_participation'] = all_forum_stat

	def _build_comment_count_by_topic(self, options):
		comment_count_by_topic = list()
		top_creators = _TopCreators( self )

		for topic in self.context.values():
			comments = self.filter_objects( topic.values() )

			count = len( comments )
			user_count = len( {c.creator for c in comments} )
			creator = self.get_student_info( topic.creator )
			created = topic.created
			comment_count_by_topic.append( self.TopicStats( topic.title, creator,
														created, count, user_count ))

			top_creators.incr_username( topic.creator.username )

		comment_count_by_topic.sort( key=lambda x: (x.created, x.title) )
		options['comment_count_by_topic'] = comment_count_by_topic
		if self.context:
			options['most_popular_topic'] = max( comment_count_by_topic, key=lambda x: x.comment_count )
			options['least_popular_topic'] = min(comment_count_by_topic, key=lambda x: x.comment_count )
		else:
			options['most_popular_topic'] = options['least_popular_topic'] = None
		options['top_creators'] = top_creators


	def _build_user_stats(self, options):
		commenters = options['top_commenters']
		creators = options['top_creators']

		for_credit_users = set(commenters.for_credit_keys()) | set(creators.for_credit_keys())
		non_credit_users = set(commenters.non_credit_keys()) | set(creators.non_credit_keys())

		for_credit_stats = self._build_user_stats_with_keys(for_credit_users, commenters, creators)
		non_credit_stats = self._build_user_stats_with_keys(non_credit_users, commenters, creators)

		options['for_credit_user_stats'] = for_credit_stats[0]
		options['non_credit_user_stats'] = non_credit_stats[0]
		only_one = for_credit_stats[1] + non_credit_stats[1]
		unique_count = for_credit_stats[2] + non_credit_stats[2]

		#Could probably break this into three parts if we want
		if unique_count:
			options['percent_users_comment_more_than_once'] = \
					"%0.1f" % ((unique_count - only_one) / unique_count * 100.0)
		else:
			options['percent_users_comment_more_than_once'] = '0.0'

	def _build_user_stats_with_keys(self, users, commenters, creators):
		"""Returns sorted user stats for the given set of users"""
		user_stats = list()
		only_one = 0
		unique_count = 0
		for uname in users:
			student_info = self.get_student_info( uname )
			stat = self.UserStats(	student_info,
									creators.get(uname, 0),
									commenters.get(uname, 0),
									commenters.get_instructor_reply_count(uname, 0) )
			user_stats.append(stat)
			if stat.total_comment_count == 1:
				only_one += 1
			if stat.total_comment_count > 0:
				unique_count += 1

		user_stats.sort( key=lambda x: x.username.display.lower() )
		return (user_stats,only_one,unique_count)

	def __call__(self):
		"""
		Return the `options` dictionary for formatting. The dictionary will
		have the following keys:

		top_commenters
			A sequence of usernames, plus the `series` representing their
			contribution to the forum.

		top_commenters_colors
			A sequence of colors to use in the pie chart for top commenters.

		comment_count_by_topic
			A sequence, sorted by created date and title, giving the `title`,
			`creator`, `created` datetime, `comment_count` and `distinct_user_count`
			participating in each topic.

		top_creators
			As with top_commenters, a sequence of usernames and the `series`
			representing their contribution of new topics.

		most/least_popular_topic
			The topic objects with the most and least activity, or None.

		user_stats
			A sequence sorted by username, of objects with `username`,
			`topics_created` and `total_comment_count`.
		"""
		self._check_access()
		options = self.options
		self._build_top_commenters(options)
		self._build_comment_count_by_topic(options)
		self._build_user_stats(options)

		return options

_TopicInfo = namedtuple('_TopicInfo',
							('topic_name', 'forum_name'))

_CommentInfo = namedtuple('_CommentInfo',
						('username', 'display', 'created', 'modified', 'content', 'parent', 'scope_name'))

COMMENT_MAX_LENGTH = 2000

@view_config(context=ICommunityHeadlineTopic,
			 name=VIEW_TOPIC_PARTICIPATION)
class TopicParticipationReportPdf(ForumParticipationReportPdf):

	report_title = _('Discussion Participation Report')

	@property
	def course(self):
		return self._course_from_forum(self.context.__parent__)

	@property
	def instructor_usernames(self):
		"All instructors from this instance and subinstances."
		# TODO We may want to do this in other reports.
		result = {x.id.lower() for x in self.course.instructors}

		subinstances = self.course.SubInstances
		if subinstances:
			for subinstance in subinstances.values():
				subinstance_instr = {x.id.lower() for x in subinstance.instructors}
				result.update( subinstance_instr )
		return result

	def _get_comment_body(self, body):
		# Need to handle canvas, escape html, etc.
		# We also need to limit character count because of table/cell/page
		# constrains in pdf.
		try:
			result = ''.join( body )
			result = html.fromstring( result )
			result = result.text_content()
		except TypeError:
			# Not sure what else we could do with these
			result = '<Non-displayable>'

		if len( result ) > COMMENT_MAX_LENGTH:
			result = result[:COMMENT_MAX_LENGTH] + '...[TRUNCATED]'
		return result

	def _get_user_scope_name(self, username):
		result = 'Public'
		if username.lower() in self.for_credit_student_usernames:
			result = 'ForCredit'
		return result

	def _get_comments_by_user(self, comments):
		"Return a dict of username to ready-to-output comments."
		results = {}
		# Gather the comments per student username
		for comment in comments:
			creator_username = comment.creator.username
			if creator_username in self.instructor_usernames:
				continue
			# Build our parent comment data
			parent = getattr( comment, 'inReplyTo', None )
			parent_comment = None
			if IGeneralForumComment.providedBy( parent ):
				scope_name = self._get_user_scope_name( parent.creator.username )
				parent_creator = self.get_student_info( parent.creator )
				parent_comment = _CommentInfo( parent_creator.username,
										parent_creator.display,
										_format_datetime( _adjust_date( parent.created ) ),
										_format_datetime( _adjust_date( parent.modified ) ),
										self._get_comment_body( parent.body ),
										None,
										scope_name )
			# Now our comment
			scope_name = self._get_user_scope_name( creator_username )
			creator = self.get_student_info( creator_username  )
			comment = _CommentInfo( creator.username,
									creator.display,
									_format_datetime( _adjust_date( comment.created ) ),
									_format_datetime( _adjust_date( comment.created ) ),
									self._get_comment_body( comment.body ),
									parent_comment,
									scope_name )

			# Note the lower to match what we're doing with enrollments.
			results.setdefault( creator_username.lower(), [] ).append( comment )
		return results

	def _get_scope_user_dict_for_course(self, user_scope_dict, user_comment_dict):
		"Returns a sorted dict of scopes to users to comments."
		scope_results = {}
		# Now populate those comments based on the enrollment scopes of those students.
		# This ensures we only get those students in our section.
		for scope_name in ('Public', 'ForCredit'):
			scope_students = user_scope_dict.get( scope_name )
			for username in scope_students:
				if username in user_comment_dict:
					scope_dict = scope_results.setdefault( scope_name, {} )
					scope_dict[ self.get_student_info( username ) ] = user_comment_dict[ username ]
			# Now sort by lower username
			scope_dict = scope_results.get( scope_name, None )
			if scope_dict is not None:
				scope_results[scope_name] = OrderedDict(
								sorted( scope_dict.items(),
										key=lambda(k,_): k.display.lower() ))

		# Now build our sorted output
		# { ScopeName : { StudentInfo : (Comments) } }
		scope_results = OrderedDict( sorted( scope_results.items() ))
		return scope_results

	def _get_section_scoped_comments(self, comments):
		"Returns a sorted dict of sections to scoped-users to comments."
		results = {}
		user_comment_dict = self._get_comments_by_user( comments )

		# We want a map of course/section name to students enrolled in that section
		# Any top-level course will break down the results by section.
		# We should have section -> scope_name -> student comments.
		subinstances = self.course.SubInstances
		if subinstances:
			for subinstance_key, subinstance in subinstances.items():
				scope_dict = _get_enrollment_scope_dict( subinstance )
				user_comment_dict_by_scope = self._get_scope_user_dict_for_course(
													scope_dict, user_comment_dict)
				# Store with a displayable key
				results[ 'Section ' + subinstance_key ] = user_comment_dict_by_scope
		else:
			scope_dict = self._get_enrollment_scope_dict
			user_comment_dict_by_scope = self._get_scope_user_dict_for_course(
													scope_dict, user_comment_dict)
			results[ self.course.__name__ ] = user_comment_dict_by_scope

		results = OrderedDict( sorted( results.items() ))
		return results


	def _build_top_commenters(self, options):
		live_objects = self.filter_objects( self.context.values() )
		buckets = _common_buckets(	live_objects,
									self,
									self.course_start_date )

		options['section_scoped_comments'] = self._get_section_scoped_comments( live_objects )
		options['top_commenters'] = buckets.top_creators
		options['group_dates'] = buckets.group_dates
		options['top_commenters_colors'] = CHART_COLORS
		all_forum_stat = _build_buckets_options(options, buckets)
		options['all_forum_participation'] = all_forum_stat

	def _build_topic_info(self):
		topic_name = self.context.title
		forum_name = self.context.__parent__.title
		return _TopicInfo( topic_name, forum_name )

	def __call__(self):
		"""
		Return the `options` dictionary for formatting. The dictionary will
		have the following keys:

		top_commenters
			A sequence of usernames, plus the `series` representing their
			contribution to the forum.
		"""
		self._check_access()
		options = self.options
		self._build_top_commenters( options )
		# This is a placeholder
		options['top_creators'] = _TopCreators( self )
		options['topic_info'] = self._build_topic_info()
		self._build_user_stats(options)

		return options

@view_config(context=ICourseInstance,
			 name=VIEW_VIDEO_REPORT)
class VideoUsageReportPdf(_AbstractReportView):

	report_title = _('Video Usage Report')
	
	def __call__(self):

		self._check_access()
		options = IVideoUsageStats(self.context)
		self.options = options
		return options

@interface.implementer(IPathAdapter, IContained)
class ReportAdapter(zcontained.Contained):

	__name__ = 'reports'

	def __init__(self, context, request):
		self.context = context
		self.request = request
		self.__parent__ = context

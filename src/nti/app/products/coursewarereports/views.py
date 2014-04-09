#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
$Id$
"""
from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from . import MessageFactory as _
from . import VIEW_STUDENT_PARTICIPATION
from . import VIEW_TOPIC_PARTICIPATION
from . import VIEW_FORUM_PARTICIPATION
from . import VIEW_COURSE_SUMMARY
from . import VIEW_ASSIGNMENT_SUMMARY

from .interfaces import IPDFReportView 

from .reports import _TopCreators
from .reports import _StudentInfo
from .reports import _common_buckets
from .reports import _CommonBuckets
from .reports import _build_buckets_options
from .reports import _get_self_assessments_for_course
from .reports import _adjust_timestamp
from .reports import _adjust_date
from .reports import _format_datetime
from .reports import _assignment_stat_for_column
from .reports import _build_question_stats

from zope import component
from zope import interface

from six import string_types
from numbers import Number

from numpy import average
from numpy import percentile

from collections import namedtuple
from collections import defaultdict

from datetime import timedelta

from itertools import chain

import BTrees

import string

import heapq

from pyramid.view import view_config
from pyramid.view import view_defaults
from pyramid.traversal import find_interface

from z3c.pagelet.browser import BrowserPagelet

from zope.catalog.interfaces import ICatalog
from zope.catalog.catalog import ResultSet 

from zope.intid.interfaces import IIntIds

from nti.utils.property import Lazy

from nti.app.assessment.interfaces import ICourseAssignmentCatalog
from nti.app.assessment.interfaces import IUsersCourseAssignmentHistory

from nti.assessment.interfaces import IQAssignment

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment
from nti.app.products.gradebook.interfaces import IGrade
from nti.app.products.gradebook.interfaces import IGradeBook
from nti.app.products.gradebook.interfaces import IGradeBookEntry

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import IDeletedObjectPlaceholder
from nti.dataserver.users.interfaces import IFriendlyNamed
from nti.dataserver.users.users import User

from nti.dataserver.contenttypes.forums.interfaces import ICommunityBoard
from nti.dataserver.contenttypes.forums.interfaces import ICommunityForum
from nti.dataserver.contenttypes.forums.interfaces import ICommunityHeadlineTopic
from nti.dataserver.contenttypes.forums.interfaces import ITopic
from nti.dataserver.contenttypes.forums.interfaces import IGeneralForumComment

from nti.dataserver.metadata_index import CATALOG_NAME

from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.dataserver.authorization import ACT_READ

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
	def __new__( self, display, username, count=None, perc=None ):
		return super(_StudentInfo,self).__new__( self,display,username,count,perc )
	

from nti.contenttypes.courses.interfaces import is_instructed_by_name
from pyramid.httpexceptions import HTTPForbidden

@view_defaults(route_name='objects.generic.traversal',
			   renderer="templates/std_report_layout.rml",
			   request_method='GET',
			   permission=ACT_READ)
@interface.implementer(IPDFReportView)
class _AbstractReportView(AbstractAuthenticatedView,
						  BrowserPagelet):

	def __init__(self, context, request):
		self.options = {}
		# Our two parents take different arguments
		AbstractAuthenticatedView.__init__(self, request)
		BrowserPagelet.__init__(self, context, request)

		if request.view_name:
			self.filename = request.view_name

	def _check_access(self):
		if not is_instructed_by_name(self.course, self.request.authenticated_userid):
			raise HTTPForbidden()

	@property
	def course(self):
		return ICourseInstance(self.context)

	@property
	def course_start_date(self):
		entry = self.course.legacy_catalog_entry
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
	def for_credit_student_usernames(self):
		restricted_id = self.course.LegacyScopes['restricted']
		restricted = Entity.get_entity(restricted_id) if restricted_id else None

		restricted_usernames = ({x.lower() for x in IEnumerableEntityContainer(restricted).iter_usernames()}
								if restricted is not None
								else set())
		return restricted_usernames - self.instructor_usernames

	@Lazy
	def open_student_usernames(self):
		return self.all_student_usernames - self.for_credit_student_usernames

	@Lazy
	def all_student_usernames(self):
		return self.all_usernames - self.instructor_usernames
	
	@Lazy
	def all_usernames(self):
		everyone = self.course.legacy_community
		everyone_usernames = {x.lower() for x in IEnumerableEntityContainer(everyone).iter_usernames()}
		return everyone_usernames

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
		ids = BTrees.family64.II.TreeSet()
		ids.update( IEnumerableEntityContainer(self.course.legacy_community).iter_intids() )
		return ids
	
	def get_student_info(self,username):
		"""Given a username, return a _StudentInfo tuple"""
		user = User.get_user( username )
		if user:
			return self.build_user_info( user )
		return _StudentInfo( username, username )

	def build_user_info(self,user):
		"""Given a user, return a _StudentInfo tuple"""
		user = IFriendlyNamed( user )
		display_name = user.alias or user.realname or user.username
		#Do not display username of open students
		user_name = "" if user.username.lower() not in self.for_credit_student_usernames else user.username
	
		return _StudentInfo( display_name, user_name )
	
	def filter_objects(self,objects):
		"""Returns a set of filtered objects"""
		return [ x for x in objects
				if not IDeletedObjectPlaceholder.providedBy( x ) ]

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
		course_board = course.Discussions
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
											if 	find_interface(x, ICommunityBoard) == course_board) )
		
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
		assignment_catalog = ICourseAssignmentCatalog(self.course)
		histories = component.getMultiAdapter((self.course, self.student_user),
											  IUsersCourseAssignmentHistory)

		asg_data = list()
		for assignment in assignment_catalog.iter_assignments():
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
			due_date = assignment.available_for_submission_ending
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


from .decorators import course_from_forum

@view_config(context=ICommunityForum,
			 name=VIEW_FORUM_PARTICIPATION)
class ForumParticipationReportPdf(_AbstractReportView):

	report_title = _('Forum Participation Report')

	agg_creators = None

	TopicStats = namedtuple('TopicStats',
							('title', 'creator', 'created', 'comment_count', 'distinct_user_count'))

	UserStats = namedtuple('UserStats',
						   ('username', 'topics_created', 'total_comment_count'))

	def _course_from_forum(self, forum):
		return course_from_forum(forum)

	@property
	def course(self):
		return self._course_from_forum(self.context)

	def _build_top_commenters(self, options):

		def _all_comments():
			for topic in self.context.values():
				#TODO this yields, right?
				#self.filter_objects( (x for x in topic.values) )
				for comment in topic.values():
					#TODO can we use filter_objects?
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
			user_count = len( {c.creator for c in comments } )
			creator = self.get_student_info( topic.creator )
			created = topic.created
			comment_count_by_topic.append( self.TopicStats( topic.title, creator, created, count, user_count ))

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

		options['for_credit_user_stats'] = fc_stats = for_credit_stats[0]
		options['non_credit_user_stats'] = nc_stats = non_credit_stats[0]
		only_one = for_credit_stats[1] + non_credit_stats[1]
		total_distinct_count = len(fc_stats) + len(nc_stats)
		
		#Could probably break this into three parts if we want
		if fc_stats or nc_stats:
			options['percent_users_comment_more_than_once'] = "%0.2f" % ((total_distinct_count - only_one) / total_distinct_count * 100.0)
		else:
			options['percent_users_comment_more_than_once'] = '0.0'

	def _build_user_stats_with_keys(self,users,commenters,creators):
		"""Returns sorted user stats for the given set of users"""
		user_stats = list()
		only_one = 0
		for uname in users:
			student_info = self.get_student_info( uname )
			stat = self.UserStats(	student_info, 
									creators.get(uname, 0), 
									commenters.get(uname, 0) )
			user_stats.append(stat)
			if stat.total_comment_count == 1:
				only_one += 1
				
		user_stats.sort( key=lambda x: x.username.display.lower() )
		return (user_stats,only_one)

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

@view_config(context=ICommunityHeadlineTopic,
			 name=VIEW_TOPIC_PARTICIPATION)
class TopicParticipationReportPdf(ForumParticipationReportPdf):

	report_title = _('Discussion Participation Report')

	@property
	def course(self):
		return self._course_from_forum(self.context.__parent__)

	def _build_top_commenters(self, options):
		live_objects = self.filter_objects( self.context.values() )
		buckets = _common_buckets(	live_objects, 
									self,
									self.course_start_date )
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
		self._build_top_commenters(options)
		# This is a placeholder
		options['top_creators'] = _TopCreators( self )
		options['topic_info'] = self._build_topic_info()
		self._build_user_stats(options)

		return options

from nti.dataserver.users import Entity
from nti.dataserver.interfaces import IEnumerableEntityContainer
from nti.contentlibrary.interfaces import IContentPackageLibrary

_EngagementPerfStat = namedtuple( '_EngagementPerfStat',
								('first','second','third','fourth'))

_EngagementQuartileStat = namedtuple( '_EngagementQuartileStat',
								('name','count','value', 'assignment_stat'))

_EngagementStats = namedtuple( '_EngagmentStats',
							( 'for_credit', 'non_credit', 'aggregate' ) )

_EngagementStat = namedtuple( '_EngagementStat',
							( 'name', 'count', 'unique_count', 'unique_perc_s', 'color' ) )

@view_config(context=ICourseInstance,
			 name=VIEW_COURSE_SUMMARY)
class CourseSummaryReportPdf(_AbstractReportView):

	report_title = _('Course Summary Report')
	assessment_aggregator = None
	engagement_aggregator = None

	def _build_enrollment_info(self, options):

		options['count_for_credit'] = len(self.for_credit_student_usernames)
		options['count_open'] = len(self.open_student_usernames)
		options['count_total'] = options['count_for_credit'] + options['count_open']

	def _build_self_assessment_data(self, options):
		md_catalog = self.md_catalog
		self_assessments = _get_self_assessments_for_course(self.course)
		self_assessment_containerids = {x.__parent__.ntiid for x in self_assessments}
		self_assessment_qsids = {x.ntiid: x for x in self_assessments}
		# We can find the self-assessments the student submitted in a few ways
		# one would be to look at the user's contained data for each containerID
		# of the self assessment and see if there is an IQAssessedQuestionSet.
		# Another would be to find all IQAssessedQuestionSets the user has completed
		# using the catalog and match them up by IDs. This might be slightly slower, but it
		# has the advantage of not knowing anything about storage.
		intids_of_submitted_qsets = md_catalog['mimeType'].apply({'any_of': ('application/vnd.nextthought.assessment.assessedquestionset',)})
		intids_of_submitted_qsets_by_students = md_catalog.family.IF.intersection( intids_of_submitted_qsets,
																				   self.intids_created_by_students )
		# As opposed to what we do for the individual student, we first
		# filter these by container ids. Unfortunately, for the bigger courses,
		# it makes almost no difference in performance (since they have the most submissions).
		# We can probably do a lot better by staying at the intid level, at the cost of
		# some complexity, as we just need three aggregate numbers.
		intids_of_objects_in_qs_containers = md_catalog['containerId'].apply({'any_of': self_assessment_containerids})
		intids_in_containers = md_catalog.family.IF.intersection(intids_of_objects_in_qs_containers,
																 intids_of_submitted_qsets_by_students )
		#qsets_by_student_in_course = [x for x in ResultSet(intids_of_submitted_qsets_by_students, self.uidutil)
		#							  if x.questionSetId in self_assessment_qsids]
		qsets_by_student_in_course = ResultSet(intids_in_containers, self.uidutil)

		title_to_count = dict()

		def _title_of_qs(qs):
			if qs.title:
				return qs.title
			return qs.__parent__.title

		for asm in self_assessments:
			title = _title_of_qs(asm)
			accum = _TopCreators( self )
			accum.aggregate_creators = self.assessment_aggregator
			accum.title = title
			title_to_count[asm.ntiid] = accum

		for submission in qsets_by_student_in_course:
			#Content may have changed such that we have an orphaned question set; move on.
			if submission.questionSetId in self_assessment_qsids:
				asm = self_assessment_qsids[submission.questionSetId]
				title_to_count[asm.ntiid].incr_username( submission.creator.username )

		options['self_assessment_data'] = sorted(title_to_count.values(),
												 key=lambda x: x.title)

	def _build_engagement_data(self, options):
		md_catalog = self.md_catalog
		intersection = md_catalog.family.IF.intersection

		intids_of_notes = md_catalog['mimeType'].apply({'any_of': ('application/vnd.nextthought.note',)})
		intids_of_hls = md_catalog['mimeType'].apply({'any_of': ('application/vnd.nextthought.highlight',)})

		intids_of_notes = intersection( intids_of_notes,
										self.intids_created_by_everyone )
		intids_of_hls = intersection( intids_of_hls,
									  self.intids_created_by_everyone )

		all_notes = intids_of_notes
		all_hls = intids_of_hls

		lib = component.getUtility(IContentPackageLibrary)
		paths = lib.pathToNTIID( self.course.legacy_content_package.ntiid )
		root = paths[0] if paths else None

		def _recur( node, accum ):
			#Get our embedded ntiids and recursively fetch our children's ntiids
			ntiid = node.ntiid
			accum.update( node.embeddedContainerNTIIDs )
			if ntiid:
				accum.add( ntiid )
			for n in node.children:	
				_recur( n, accum )

		containers_in_course = set()
		if root:
			_recur( root,containers_in_course )
		containers_in_course.discard( None )

		#Now we should have our whole tree of ntiids, intersect with our vals
		intids_of_objects_in_course_containers = md_catalog['containerId'].apply({'any_of': containers_in_course})

		intids_of_notes = intersection( intids_of_notes,
										intids_of_objects_in_course_containers )
		intids_of_hls = intersection( intids_of_hls,
									  intids_of_objects_in_course_containers )

		#We could filter notes and highlights (exclude deleted)
		#If we want top noters/highlighters, we should use TopCreators
		notes = ResultSet( intids_of_notes, self.uidutil )
		note_creators = _TopCreators( self )
		for note in notes:
			note_creators.incr_username( note.creator.username )
		
		for_credit_note_count = note_creators.for_credit_total
		non_credit_note_count = note_creators.non_credit_total
		total_note_count = note_creators.total
		
		for_credit_unique_note = note_creators.unique_contributors_for_credit
		for_credit_perc_s_note = note_creators.for_credit_percent_contributed_str()
		
		non_credit_unique_note = note_creators.unique_contributors_non_credit
		non_credit_perc_s_note = note_creators.non_credit_percent_contributed_str()
		
		total_unique_note = note_creators.unique_contributors
		total_perc_s_note = note_creators.percent_contributed_str()

		#Highlights
		highlights = ResultSet(intids_of_hls, self.uidutil)
		hl_creators = _TopCreators( self )
		for hl in highlights:
			hl_creators.incr_username( hl.creator.username )
		
		for_credit_hl_count = hl_creators.for_credit_total
		non_credit_hl_count = hl_creators.non_credit_total
		total_hl_count = hl_creators.total
		
		for_credit_unique_hl = hl_creators.unique_contributors_for_credit
		for_credit_perc_s_hl = hl_creators.for_credit_percent_contributed_str()
		
		non_credit_unique_hl = hl_creators.unique_contributors_non_credit
		non_credit_perc_s_hl = hl_creators.non_credit_percent_contributed_str()
		
		total_unique_hl = hl_creators.unique_contributors
		total_perc_s_hl = hl_creators.percent_contributed_str()

		#Discussions/comments
		discussion_creators = _TopCreators( self )
		comment_creators = _TopCreators( self )

		for forum in self.course.Discussions.values():
			for discussion in forum.values():
				discussion_creators.incr_username( discussion.creator.username )
				for comment in discussion.values():
					if not IDeletedObjectPlaceholder.providedBy( comment ):
						comment_creators.incr_username( comment.creator.username )

		#Discussions
		for_credit_discussion_count = discussion_creators.for_credit_total
		non_credit_discussion_count = discussion_creators.non_credit_total
		total_discussion_count = discussion_creators.total
		
		for_credit_unique_discussion = discussion_creators.unique_contributors_for_credit
		for_credit_perc_s_discussion = discussion_creators.for_credit_percent_contributed_str()
		
		non_credit_unique_discussion = discussion_creators.unique_contributors_non_credit
		non_credit_perc_s_discussion = discussion_creators.non_credit_percent_contributed_str()
		
		total_unique_discussion = discussion_creators.unique_contributors
		total_perc_s_discussion = discussion_creators.percent_contributed_str()

		#Comments
		for_credit_comment_count = comment_creators.for_credit_total
		non_credit_comment_count = comment_creators.non_credit_total
		total_comment_count = comment_creators.total
		
		for_credit_unique_comment = comment_creators.unique_contributors_for_credit
		for_credit_perc_s_comment = comment_creators.for_credit_percent_contributed_str()
		
		non_credit_unique_comment = comment_creators.unique_contributors_non_credit
		non_credit_perc_s_comment = comment_creators.non_credit_percent_contributed_str()
		
		total_unique_comment = comment_creators.unique_contributors
		total_perc_s_comment = comment_creators.percent_contributed_str()
		
		note_color = CHART_COLORS[0]
		hl_color = CHART_COLORS[5]
		discussion_color = CHART_COLORS[2]
		comments_color = CHART_COLORS[1]
		
		for_credit_notes =  _EngagementStat( 'Notes', for_credit_note_count, for_credit_unique_note, for_credit_perc_s_note, note_color )
		for_credit_hls = _EngagementStat( 'Highlights', for_credit_hl_count, for_credit_unique_hl, for_credit_perc_s_hl, hl_color )
		for_credit_discussions = _EngagementStat( 'Discussions Created', for_credit_discussion_count, for_credit_unique_discussion, for_credit_perc_s_discussion, discussion_color )
		for_credit_comments = _EngagementStat( 'Discussion Comments', for_credit_comment_count, for_credit_unique_comment, for_credit_perc_s_comment, comments_color )
		for_credit_list = [ for_credit_notes, for_credit_hls, for_credit_discussions, for_credit_comments ]
		activity = sum( [x.count for x in for_credit_list] )
		for_credit_stats = for_credit_list if activity else []

		non_credit_notes = _EngagementStat( 'Notes',  non_credit_note_count, non_credit_unique_note, non_credit_perc_s_note, note_color )
		non_credit_hls = _EngagementStat( 'Highlights', non_credit_hl_count, non_credit_unique_hl, non_credit_perc_s_hl, hl_color )
		non_credit_discussions = _EngagementStat( 'Discussions Created', non_credit_discussion_count, non_credit_unique_discussion, non_credit_perc_s_discussion, discussion_color )
		non_credit_comments = _EngagementStat( 'Discussion Comments', non_credit_comment_count, non_credit_unique_comment, non_credit_perc_s_comment, comments_color )
		non_credit_list = [ non_credit_notes, non_credit_hls, non_credit_discussions, non_credit_comments ]
		activity = sum( [x.count for x in non_credit_list] )
		non_credit_stats = non_credit_list if activity else []

		total_notes = _EngagementStat( 'Notes', total_note_count, total_unique_note, total_perc_s_note, note_color )
		total_hls = _EngagementStat( 'Highlights', total_hl_count, total_unique_hl, total_perc_s_hl, hl_color )
		total_discussions = _EngagementStat( 'Discussions Created', total_discussion_count, total_unique_discussion, total_perc_s_discussion, discussion_color )
		total_comments = _EngagementStat( 'Discussion Comments', total_comment_count, total_unique_comment, total_perc_s_comment, comments_color )
		aggregate_list = [ total_notes, total_hls, total_discussions, total_comments ]
		activity = sum( [x.count for x in aggregate_list] )
		aggregate_stats = aggregate_list if activity else []

		options['engagement_data'] = _EngagementStats( for_credit_stats, non_credit_stats, aggregate_stats )

# 		outline = self.course.Outline
# 		def _recur(node, accum):
# 			ntiid = getattr(node, 'ContentNTIID', getattr(node, '_v_ContentNTIID', None))
# 			if ntiid:
# 				accum.add(ntiid)
# 			for n in node.values():
# 				_recur(n, accum)

#		Exclude engagement_by_place data until we fully flesh out the details
# 		data = list()
# 
# 		stat = namedtuple('Stat',
# 						  ('title', 'note_count', 'hl_count'))
# 
# 		for unit in outline.values():
# 			for lesson in unit.values():
# 				ntiids = set()
# 				_recur(lesson, ntiids)
# 				for x in list(ntiids):
# 					try:
# 						kid = lib.pathToNTIID(x)[-1]
# 						ntiids.update( kid.embeddedContainerNTIIDs )
# 					except TypeError:
# 						pass
# 
# 					for kid in lib.childrenOfNTIID(x):
# 						ntiids.add(kid.ntiid)
# 						ntiids.update(kid.embeddedContainerNTIIDs)
# 				ntiids.discard(None)
# 				local_notes = md_catalog['containerId'].apply({'any_of': ntiids})
# 				local_notes = intersection(local_notes, all_notes)
# 				local_hls = md_catalog['containerId'].apply({'any_of': ntiids})
# 				local_hls = intersection(local_hls, all_hls)
# 
# 				data.append( stat( lesson.title, len(local_notes), len(local_hls)) )
# 
# 		# Keep these in lesson order
# 		options['placed_engagement_data'] = data


	def _build_assignment_data(self, options, filter=None):
		gradebook = IGradeBook(self.course)
		assignment_catalog = ICourseAssignmentCatalog(self.course)

		stats = list()
		for asg in assignment_catalog.iter_assignments():
			column = gradebook.getColumnForAssignmentId(asg.ntiid)
			stats.append(_assignment_stat_for_column(self, column, filter))

		stats.sort(key=lambda x: (x.due_date is None, x.due_date, x.title))
		return stats


	def _build_top_commenters(self, options):

		forum_stats = dict()
		agg_creators = _TopCreators( self )
		agg_creators.aggregate_creators = self.engagement_aggregator

		for key, forum in self.course.Discussions.items():
			forum_stat = forum_stats[key] = dict()
			forum_stat['forum'] = forum
			forum_view = ForumParticipationReportPdf(forum, self.request)
			forum_view.agg_creators = agg_creators
			forum_view.options = forum_stat
			
			last_mod_ts = forum.NewestDescendantCreatedTime
			last_mod_time = _adjust_timestamp( last_mod_ts ) if last_mod_ts > 0 else None
			forum_stat['last_modified'] = _format_datetime( last_mod_time ) if last_mod_time else 'N/A'
			
			forum_view.for_credit_student_usernames = self.for_credit_student_usernames
			forum_view()
			forum_stat['discussion_count'] = len( self.filter_objects( forum.values() ) )
			forum_stat['total_comments'] = sum( [x.comment_count for x in forum_stat['comment_count_by_topic']] )
			
		#Need to accumulate these
		#TODO rework this
		acc_week = BTrees.family64.II.BTree()
		
		#Aggregate weekly numbers
		for key, stat in forum_stats.items():
			forum_stat = stat['all_forum_participation']
			by_week = forum_stat.forum_objects_by_week_number
			for week,val in by_week.items():
				if week in acc_week:
					acc_week[week] += val
				else:
					acc_week[week] = val
		
		#Now we have to come up with our categories
		accum_dates_list = ( x['group_dates'] for x in forum_stats.values() )
		accum_dates = list( chain.from_iterable( accum_dates_list ) )
		accum_dates = sorted( accum_dates )
		dates = []
		
		start_date = self.course_start_date.date()
		start_monday = start_date - timedelta( days=start_date.weekday() )
		old_week_num = None
		#We have our sorted dates now. Just need to normalize them by week.
		#FIXME and clean this up
		for k in accum_dates:
			group_monday = k - timedelta( days=k.weekday() )
			week_num = ( (group_monday - start_monday).days // 7 )

			if old_week_num is None:
				old_week_num = week_num
				dates.append( group_monday )

			if week_num != old_week_num:
				#Check for week gaps and fill
				for f in range(old_week_num - week_num + 1, 0):
					#Add negative weeks to retain order
					old_monday = group_monday + timedelta( weeks=1 * f )
					dates.append( old_monday )
				dates.append( group_monday )	
				old_week_num = week_num
			
		new_buckets = _CommonBuckets(None, acc_week, None, dates)
		agg_stat = _build_buckets_options({},new_buckets)
		options['aggregate_forum_stats'] = agg_stat

		options['forum_stats'] = [x[1] for x in sorted(forum_stats.items())]
		
		options['aggregate_creators'] = agg_creators
		options['top_commenters_colors'] = CHART_COLORS

	def _build_engagement_perf(self,options):
		"""
		Get engagement data:
			- Self-assessments by user (2x)
			- Comments/discussion creators (1x)
			- (Notes/highlights)
		Stuff into buckets by user
			- Quartile might be too low?
		For each assignment, see how each quartile performed
		Return 'engagement_to_performance' (EngagementPerfStats)
			-Each assignment (title,count)
				-QuartileStat (first,second,third,fourth)
					-Name
					-Boundary
					-ForCredit/NonCredit (assignmentstat)
						-Average
						-Median
						-Max
						-Min
		TODO: toggle these numbers
			-verify
			-add stats by quartile (count, avg(assessment), avg(comment_count), quartile_val) Engagement_stat	
			-		
		"""
		agg_map = self.engagement_aggregator._data
		
		for k,v in self.assessment_aggregator._data.items():
			#self-assessments are weighted 2
			#comments are weighted 1
			weighted_val = 2 * v
			if k in agg_map:
				agg_map[k] += weighted_val
			else:
				agg_map[k] = weighted_val 
				
		quartiles = percentile( [x[1] for x in agg_map.items()], [75, 50, 25] ) 		

		first = list()
		second = list()
		third = list()
		fourth = list()
		
		for x,v in map.items():
			if v >= quartiles[0]:
				first.append( x )
			elif v >= quartiles[1]:
				second.append( x )
			elif v >= quartiles[2]:
				third.append( x )
			else:
				fourth.append( x )

		first_stats = self._build_assignment_data(options, first)	
		second_stats = self._build_assignment_data(options, second)	
		third_stats = self._build_assignment_data(options, third)	
		fourth_stats = self._build_assignment_data(options, fourth)		
		
		first_quart = _EngagementQuartileStat( 'First', len(first), quartiles[0], first_stats )
		second_quart = _EngagementQuartileStat( 'Second', len(second), quartiles[1], second_stats )
		third_quart = _EngagementQuartileStat( 'Third', len(third), quartiles[2], third_stats )
		fourth_quart = _EngagementQuartileStat( 'Fourth', len(fourth), 0, fourth_stats )
		
		options['engagement_to_performance'] = _EngagementPerfStat( first_quart, second_quart, third_quart, fourth_quart )		

	def __call__(self):
		self._check_access()
		options = self.options
		
		#self.assessment_aggregator = _TopCreators(self.for_credit_student_usernames, self.get_student_info)
		#self.engagement_aggregator = _TopCreators(self.for_credit_student_usernames, self.get_student_info)
		self._build_engagement_data(options)
		self._build_enrollment_info(options)
		self._build_self_assessment_data(options)
		options['assignment_data'] = self._build_assignment_data(options)
		self._build_top_commenters(options)
		#Must do this last
		#self._build_engagement_perf(options)
		options['engagement_to_performance'] = ()
		return options

from nti.app.assessment.interfaces import IUsersCourseAssignmentHistoryItem
from nti.assessment.interfaces import IQAssessedQuestionSet
from nti.assessment.interfaces import IQMultipleChoicePart
from nti.assessment.interfaces import IQMultipleChoiceMultipleAnswerPart
from nti.contentfragments.interfaces import IPlainTextContentFragment

class _AnswerStat(object):
	"""Holds stat and display information for a particular answer."""
	letter_prefix = None
	count = 0
	perc_s = None
	
	def __init__(self, answer, is_correct):
		self.answer = answer
		self.is_correct = is_correct
		self.count = 1

#FIXME oof, we already have two _QuestionStats; I must have been tired.
class _QuestionStat(object):
	"""Holds stat and display information for a particular question."""
	submission_count = 0
	answer_stat = {}
	
	def __init__(self, answer_stat, submission_count):
		self.answer_stat = answer_stat
		self.submission_count = submission_count

@view_config(context=IGradeBookEntry,
			 name=VIEW_ASSIGNMENT_SUMMARY)
class AssignmentSummaryReportPdf(_AbstractReportView):

	report_title = _('Assignment Summary Report')

	def _build_assignment_data(self, options):
		stats = [_assignment_stat_for_column(self, self.context)]
		options['assignment_data'] = stats

	def _add_multiple_choice_to_answer_stats(self,answer_stats,response,question_part,check_correct):
		"""Adds the multiple choice response to our answer_stats"""
		#We could have empty strings or 'None' here; slot that in our 'empty' answer area
		response_val = question_part.choices[response] if response is not None and response != '' else ''
		self._add_val_to_answer_stats(answer_stats, response_val, check_correct)

	def _add_val_to_answer_stats(self,answer_stats,response,check_correct):
		"""Adds a response value to our answer_stats"""
		if isinstance(response, string_types):
			response = IPlainTextContentFragment(response)
			
		if response in answer_stats:
			answer_stats[response].count += 1
		else:
			is_correct = check_correct()
			answer_stats[response] = _AnswerStat(response,is_correct)

	def _build_question_data(self, options):
		assignment = component.queryUtility(IQAssignment, name=self.context.AssignmentId)
		if assignment is None:
			#Maybe this is something without an assignment, like Attendance?
			#In ou-alpha, CS1300-exercise1
			return

		ordered_questions = []
		qids_to_q = {}
		for apart in assignment.parts:
			for q in apart.question_set.questions:
				ordered_questions.append(q)
				qids_to_q[q.ntiid] = q

		column = self.context
		submissions = {} 
		assessed_values = {}

		for grade in column.values():
			try:
				history = IUsersCourseAssignmentHistoryItem(grade)
			except TypeError: # Deleted user
				continue

			submission = history.Submission
			
			pending = history.pendingAssessment
			for set_submission in submission.parts:
				for question_submission in set_submission.questions:
					question = qids_to_q[question_submission.questionId]
					
					if question_submission.questionId in submissions:
						question_stat = submissions[question_submission.questionId]
						answer_stats = question_stat.answer_stat
						question_stat.submission_count += 1
					else:
						answer_stats = {}
						submissions[question_submission.questionId] = _QuestionStat( answer_stats, 1 )

					for idx in range(len(question.parts)):
						question_part = question.parts[idx] 
						response = question_submission.parts[idx]
						
						if idx in answer_stats:
							answer_stat = answer_stats[idx]
						else:
							answer_stats[idx] = answer_stat = {}

						if (	IQMultipleChoicePart.providedBy(question_part)
							and not IQMultipleChoiceMultipleAnswerPart.providedBy(question_part)
							and isinstance(response, int)):
							# We have indexes into single multiple choice answers
							# convert int indexes into actual values
							self._add_multiple_choice_to_answer_stats( 	answer_stat, 
																		response, 
																		question_part,
																		lambda: response == question_part.solutions[0].value )
						elif (	IQMultipleChoicePart.providedBy(question_part)
							and IQMultipleChoiceMultipleAnswerPart.providedBy(question_part)
							and response):		
							# We are losing empty responses
							# The solutions should be int indexes, as well as our responses
							for r in response:
								self._add_multiple_choice_to_answer_stats( 	answer_stat, 
																			r, 
																			question_part,
																			lambda: r in question_part.solutions[0].value )
					#TODO We should be able to handle freeform multiple answer as well
						# Solutions and respones should be a list of strings
						# Freeform multi-answer strings
						#	-list of responses
						#	-list of solutions
					#TODO Can we handle matching (and ordering)
					#	For those, each answer available will have correct and incorrect answers
						elif isinstance(response, string_types):
							# Freeform answers
							response = response.lower()	
							solution = question_part.solutions[0].value
						
							#TODO What case does this occur in?			
							solution = solution.lower() if isinstance(solution, string_types) else solution
							self._add_val_to_answer_stats( 	answer_stat,
															response,
															lambda: solution == response )

			for maybe_assessed in pending.parts:
				if not IQAssessedQuestionSet.providedBy(maybe_assessed):
					continue
				for assessed_question in maybe_assessed.questions:
					
					for idx in range(len(assessed_question.parts)):
						assessed_part = assessed_question.parts[idx]
						val = assessed_part.assessedValue
						#We may not have a grade yet
						if val is not None:
							if assessed_question.questionId in assessed_values:
								question_parts = assessed_values[assessed_question.questionId]
							else:
								assessed_values[assessed_question.questionId] = question_parts = {}
								
							if idx in question_parts:
								question_parts[idx].append( val )
							else:	
								question_parts[idx] = [val]

		options['question_stats'] = _build_question_stats( ordered_questions, submissions, assessed_values )


	def __call__(self):
		self._check_access()
		options = self.options
		self._build_assignment_data(options)
		self._build_question_data(options)
		return options

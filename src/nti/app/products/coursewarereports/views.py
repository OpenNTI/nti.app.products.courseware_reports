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

from zope import component
from zope import interface

from six import string_types
from numbers import Number

from itertools import groupby
from collections import namedtuple
from collections import defaultdict
from datetime import datetime

import BTrees
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
from nti.app.assessment.interfaces import ICourseAssessmentItemCatalog

from nti.assessment.interfaces import IQAssignment
from nti.assessment.interfaces import IQuestionSet

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseAdministrativeLevel
from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment
from nti.app.products.gradebook.interfaces import IGrade
from nti.app.products.gradebook.interfaces import IGradeBook
from nti.app.products.gradebook.interfaces import IGradeBookEntry
from nti.dataserver.interfaces import IUser

from nti.dataserver.contenttypes.forums.interfaces import ICommunityBoard
from nti.dataserver.contenttypes.forums.interfaces import ICommunityForum
from nti.dataserver.contenttypes.forums.interfaces import ICommunityHeadlineTopic
from nti.dataserver.contenttypes.forums.interfaces import ITopic
from nti.dataserver.contenttypes.forums.interfaces import IGeneralForumComment

from nti.dataserver.metadata_index import CATALOG_NAME
from nti.zope_catalog.datetime import TimestampNormalizer

from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.dataserver.authorization import ACT_READ

def _get_self_assessments_for_course(course):
	"""
	Given an :class:`.ICourseInstance`, return a list of all
	the \"self assessments\" in the course. Self-assessments are
	defined as top-level question sets that are not used within an assignment
	in the course.
	"""
	# NOTE: This is pretty tightly coupled to the implementation
	# and the use of one content package (?). See NonAssignmentsByOutlineNodeDecorator
	# (TODO: Find a way to unify this)
	catalog = ICourseAssessmentItemCatalog(course)

	# Not only must we filter out assignments, we must filter out the
	# question sets that they refer to; we assume such sets are only
	# used by the assignment.
	# XXX FIXME not right.

	result = list()

	qsids_to_strip = set()

	for item in catalog.iter_assessment_items():
		if IQAssignment.providedBy(item):
			qsids_to_strip.add(item.ntiid)
			for assignment_part in item.parts:
				question_set = assignment_part.question_set
				qsids_to_strip.add(question_set.ntiid)
				for question in question_set.questions:
					qsids_to_strip.add(question.ntiid)
		elif not IQuestionSet.providedBy(item):
			qsids_to_strip.add(item.ntiid)
		else:
			result.append(item)

	# Now remove the forbidden
	result = [x for x in result if x.ntiid not in qsids_to_strip]
	return result

_CommonBuckets = namedtuple('_CommonBuckets',
					  ('count_by_day', 'count_by_week_number', 'top_creators'))

import heapq
class _TopCreators(object):
	total = 0
	title = ''
	max_contributors = None

	def __init__(self):
		self._data = BTrees.family64.OI.BTree()

	def _get_largest(self):
		# Returns the top commenter names, up to (arbitrarily) 15
		# of them, with the next being 'everyone else'
		# In typical data, 'everyone else' far overwhelms
		# the top 15 commenters, so we are giving it a small value
		# (one-eigth of the pie),
		# but including it as a percentage in its label
		# TODO: Better way to do this?
		largest = heapq.nlargest(15, self._data.items(), key=lambda x: x[1])
		# Give percentages to the usernames
		largest = [('%s (%0.1f%%)' % (x[0],(x[1] / self.total) * 100), x[1]) for x in largest]
		if len(self._data) > len(largest):
			# We didn't account for everyone, we need to
			largest_total = sum( (x[1] for x in largest) )
			remainder = self.total - largest_total
			# TODO: Localize and map this
			percent = (remainder / self.total) * 100
			largest.append( ('Others (%0.1f%%)' % percent, largest_total // 8) )
		return largest

	def __iter__(self):
		return (x[0] for x in self._get_largest())

	def __bool__(self):
		return bool(self._data)
	__nonzero__ = __bool__

	def series(self):
		return ' '.join( ('%d' % x[1] for x in self._get_largest()) )

	def incr_username(self, username):
		self.total += 1
		if username in self._data:
			self._data[username] += 1
		else:
			self._data[username] = 1


	def keys(self):
		return self._data.keys()

	def get(self, key, default=None):
		return self._data.get(key, default)

	def average_count(self):
		if self.total:
			return self.total / len(self._data)
		return 0

	def average_count_str(self):
		return "%0.1f" % self.average_count()

	def percent_contributed(self):
		if self.max_contributors is None:
			return 100
		return (len(self.keys()) / self.max_contributors) * 100.0

	def percent_contributed_str(self):
		return "%0.1f" % self.percent_contributed()

def _common_buckets(objects):
	"""
	Given a list of :class:`ICreated` objects,
	return a :class:`_CommonBuckets` containing three members:
	a map from a normalized timestamp for each day to the number of
	objects created that day, and a map from an ISO week number
	to the number of objects created that week,
	and an instance of :class:`_TopCreators`.

	The argument can be an iterable sequence, we sort a copy.

	"""
	# Group the forum objects by day
	day_normalizer = TimestampNormalizer(TimestampNormalizer.RES_DAY)
	day_key = lambda x: int(day_normalizer.value(x.createdTime))

	objects = sorted(objects, key=day_key)

	forum_objects_by_day = BTrees.family64.II.BTree()
	forum_objects_by_week_number = BTrees.family64.II.BTree()
	top_creators = _TopCreators()

	for k, g in groupby(objects, day_key):
		group = list(g)
		count = len(group)
		for o in group:
			top_creators.incr_username(o.creator)

		forum_objects_by_day[k] = count

		year_num, week_num, _ = datetime.utcfromtimestamp(k).isocalendar()
		# Because sometimes forums can wrap around years (e.g, start
		# in the fall of 2013, run through the spring of 2014),
		# we use week numbers that include the year so everything
		# stays in order.
		# NOTE: This is still not correct, leading to a large gap
		# between years (as the weeks from 52 to 100 do not exist)
		week_num = year_num * 100 + week_num
		if week_num in forum_objects_by_week_number:
			forum_objects_by_week_number[week_num] += count
		else:
			forum_objects_by_week_number[week_num] = count

	return _CommonBuckets(forum_objects_by_day, forum_objects_by_week_number, top_creators)

def _build_buckets_options(options, buckets):
	forum_objects_by_week_number = buckets.count_by_week_number
	forum_objects_by_day = buckets.count_by_day

	options['forum_objects_by_day'] = forum_objects_by_day
	options['forum_objects_by_week_number'] = forum_objects_by_week_number

	if forum_objects_by_week_number:
		def as_series():
			rows = ['%d    %d' % (k,forum_objects_by_week_number.get(k, 0))
					for k in range(forum_objects_by_week_number.minKey(),
								   forum_objects_by_week_number.maxKey() + 1)
					if k in forum_objects_by_week_number]
			return '\n'.join(rows)
		options['forum_objects_by_week_number_series'] = as_series
		options['forum_objects_by_week_number_max'] = _max = max(forum_objects_by_week_number.values()) + 1
		options['forum_objects_by_week_number_value_min'] = forum_objects_by_week_number.minKey() - 1
		options['forum_objects_by_week_number_value_max'] = forum_objects_by_week_number.maxKey() + 1
		if _max > 30:
			# If we have too many values, we have to pick how often we label, otherwise
			# they won't all fit on the chart and we wind up with overlapping unreadable
			# blur.
			step = _max // 10
		else:
			step = 1
		options['forum_objects_by_week_number_y_step'] = step

		# How many weeks elapsed?
		if forum_objects_by_week_number.maxKey() - forum_objects_by_week_number.minKey() > 10:
			step = (forum_objects_by_week_number.maxKey() - forum_objects_by_week_number.minKey()) // 5
		else:
			step = 1
		options['forum_objects_by_week_number_x_step'] = step

	else:
		options['forum_objects_by_week_number_series'] = ''
		options['forum_objects_by_week_number_max'] = 0
		options['forum_objects_by_week_number_value_min'] = 0
		options['forum_objects_by_week_number_value_max'] = 0

FORUM_OBJECT_MIMETYPES = ['application/vnd.nextthought.forums.generalforumcomment',
						  'application/vnd.nextthought.forums.communityforumcomment',
						  'application/vnd.nextthought.forums.communitytopic',
						  'application/vnd.nextthought.forums.communityheadlinetopic']

ENGAGEMENT_OBJECT_MIMETYPES = ['application/vnd.nextthought.note',
							   'application/vnd.nextthought.highlight']

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


	@property
	def course(self):
		return ICourseInstance(self.context)

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
	def for_credit_student_usernames(self):
		restricted_id = self.course.LegacyScopes['restricted']
		restricted = Entity.get_entity(restricted_id) if restricted_id else None

		restricted_usernames = ({x for x in IEnumerableEntityContainer(restricted).iter_usernames()}
								if restricted is not None
								else set())
		return restricted_usernames

	@Lazy
	def open_student_usernames(self):
		return self.all_student_usernames - self.for_credit_student_usernames

	@Lazy
	def all_student_usernames(self):
		everyone = self.course.legacy_community
		everyone_usernames = {x for x in IEnumerableEntityContainer(everyone).iter_usernames()}
		student_usernames = everyone_usernames - {x.id for x in self.course.instructors}
		return student_usernames

	@Lazy
	def count_all_students(self):
		return len(self.all_student_usernames)
	@Lazy
	def count_credit_students(self):
		return len(self.for_credit_student_usernames)

	@Lazy
	def all_user_intids(self):
		ids = BTrees.family64.II.TreeSet()
		ids.update( IEnumerableEntityContainer(self.course.legacy_community).iter_intids() )
		return ids


@view_config(context=ICourseInstanceEnrollment,
			 name=VIEW_STUDENT_PARTICIPATION)
class StudentParticipationReportPdf(_AbstractReportView):

	report_title = _('Student Participation Report')

	TopicCreated = namedtuple('TopicCreated',
							  ('topic', 'topic_name', 'forum_name', 'created'))
	AssignmentInfo = namedtuple('AssignmentInfo',
								('title', 'submitted', 'grade_value', 'history', 'due_date'))

	@Lazy
	def student_user(self):
		return IUser(self.context)
	@Lazy
	def intids_created_by_student(self):
		return self.md_catalog['creator'].apply({'any_of': (self.context.Username,)})

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
		forum_objects_created_by_student_in_course = [x for x in forum_objects_created_by_student
													  if find_interface(x, ICommunityBoard) == course_board]
		# Group the forum objects by day and week
		time_buckets = _common_buckets(forum_objects_created_by_student_in_course)

		# Tabular breakdown of what topics the user created in what forum
		# and how many comments in which topics (could be bulkData or actual blockTable)
		topics_created = []
		comment_count_by_topic = defaultdict(int)
		for x in forum_objects_created_by_student_in_course:
			if ITopic.providedBy(x):
				info = self.TopicCreated( x, x.title, x.__parent__.title, x.created )
				topics_created.append(info)
			elif IGeneralForumComment.providedBy(x):
				comment_count_by_topic[x.__parent__] += 1

		topics_created.sort(key=lambda x: (x.forum_name, x.topic_name))
		options['topics_created'] = topics_created
		options['total_forum_objects_created'] = len(forum_objects_created_by_student_in_course)
		options['comment_count_by_topic'] = sorted(comment_count_by_topic.items(),
												   key=lambda x: (x[0].__parent__.title, x[0].title))
		_build_buckets_options(options, time_buckets)

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
			asg_data.append(self.AssignmentInfo(assignment.title, submitted,
												grade_value, history_item,
												assignment.available_for_submission_ending))

		asg_data.sort(key=lambda x: (x.due_date, x.title))
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

		forum_objects_by_week_number
			A BTree mapping the ISO week number to the number of objects the user
			created in forums that week.

		"""
		# Collect data and return it in a form to be rendered
		# (a dictionary containing data and callable objects)
		options = self.options
		self._build_forum_data(options)

		# Each self-assessment and how many times taken (again bulkData)
		self._build_self_assessment_data(options)

		# Table of assignment history and grades for all assignments in course
		self._build_assignment_data(options)

		self.options = options
		return options


from reportlab.lib import colors

@view_config(context=ICommunityForum,
			 name=VIEW_FORUM_PARTICIPATION)
class ForumParticipationReportPdf(_AbstractReportView):

	report_title = _('Forum Participation Report')

	TopicStats = namedtuple('TopicStats',
							('title', 'creator', 'created', 'comment_count', 'distinct_user_count'))

	UserStats = namedtuple('UserStats',
						   ('username', 'topics_created', 'total_comment_count'))

	def _course_from_forum(self, forum):
		board = forum.__parent__
		community = board.__parent__
		courses = ICourseAdministrativeLevel(community)
		if courses:
			# Assuming only one
			course = list(courses.values())[0]
			assert course.Discussions == board
			return course

	@property
	def course(self):
		return self._course_from_forum(self.context)

	def _build_top_commenters(self, options):
		def _all_comments():
			for topic in self.context.values():
				for comment in topic.values():
					yield comment
		buckets = _common_buckets(_all_comments())
		options['top_commenters'] = buckets.top_creators
		# Obviously we'll want better color choices than "random"
		options['top_commenters_colors'] = colors.getAllNamedColors().keys()
		_build_buckets_options(options, buckets)

	def _build_comment_count_by_topic(self, options):
		comment_count_by_topic = list()
		top_creators = _TopCreators()
		for topic in self.context.values():
			count = len(topic)
			user_count = len({c.creator for c in topic.values()})
			creator = topic.creator
			created = topic.created
			comment_count_by_topic.append( self.TopicStats( topic.title, creator, created, count, user_count ))

			top_creators.incr_username(topic.creator)

		comment_count_by_topic.sort( key=lambda x: (x.created, x.title) )
		options['comment_count_by_topic'] = comment_count_by_topic
		if self.context:
			options['most_popular_topic'] = max(self.context.values(), key=len)
			options['least_popular_topic'] = min(self.context.values(), key=len)
		else:
			options['most_popular_topic'] = options['least_popular_topic'] = None
		options['top_creators'] = top_creators


	def _build_user_stats(self, options):
		commenters = options['top_commenters']
		creators = options['top_creators']

		everyone_that_did_something = set(commenters.keys()) | set(creators.keys())

		user_stats = list()
		only_one = 0
		for uname in sorted(everyone_that_did_something):
			stat = self.UserStats(uname, creators.get(uname, 0), commenters.get(uname, 0) )
			user_stats.append(stat)
			if stat.total_comment_count == 1:
				only_one += 1

		options['user_stats'] = user_stats
		if user_stats:
			options['percent_users_comment_more_than_once'] = "%0.2f" % (((len(user_stats) - only_one) / len(user_stats)) * 100.0)
		else:
			options['percent_users_comment_more_than_once'] = '0.0'

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
		options = self.options
		self._build_top_commenters(options)
		self._build_comment_count_by_topic(options)
		self._build_user_stats(options)

		return options


@view_config(context=ICommunityHeadlineTopic,
			 name=VIEW_TOPIC_PARTICIPATION)
class TopicParticipationReportPdf(ForumParticipationReportPdf):

	report_title = _('Topic Participation Report')

	@property
	def course(self):
		return self._course_from_forum(self.context.__parent__)

	def _build_top_commenters(self, options):
		buckets = _common_buckets(self.context.values())
		options['top_commenters'] = buckets.top_creators
		# Obviously we'll want better color choices than "random"
		options['top_commenters_colors'] = colors.getAllNamedColors().keys()
		_build_buckets_options(options, buckets)

	def __call__(self):
		"""
		Return the `options` dictionary for formatting. The dictionary will
		have the following keys:

		top_commenters
			A sequence of usernames, plus the `series` representing their
			contribution to the forum.
		"""
		options = self.options
		self._build_top_commenters(options)
		options['top_creators'] = dict()
#		self._build_comment_count_by_topic(options)
		self._build_user_stats(options)

		return options

from nti.dataserver.users import Entity
from nti.dataserver.interfaces import IEnumerableEntityContainer
from nti.contentlibrary.interfaces import IContentPackageLibrary
from numpy import asarray
from numpy import average
from numpy import median
from numpy import std
from numpy import var


_AssignmentStat = namedtuple('_AssignmentStat',
							 ('title', 'count',
							  'avg_grade', 'median_grade',
							  'std_grade', 'var_grade',
							  'attempted', 'for_credit_attempted'))

def _assignment_stat_for_column(self, column):
	count = len(column)
	keys = set(column)

	grade_points = [x.value if isinstance(x.value, Number) else float(x.value.split()[0])
					for x in column.values()
					if x.value]

	if grade_points:
		grade_points = asarray(grade_points)
		avg_grade = average(grade_points)
		avg_grade_s = '%0.1f' % avg_grade

		median_grade = median(grade_points)
		median_grade_s = '%0.1f' % median_grade

		std_grade = std(grade_points)
		std_grade_s = '%0.1f' % std_grade
		var_grade = var(grade_points)
	else:
		avg_grade_s = median_grade_s = std_grade_s = var_grade = 'N/A'

	if self.count_all_students:
		per_attempted = (count / self.count_all_students) * 100.0
		per_attempted_s = '%0.1f' % per_attempted
	else:
		per_attempted_s = 'N/A'

	# TODO: Case sensitivity issue?
	for_credit_atempted = self.for_credit_student_usernames.intersection(keys)
	if self.count_credit_students:
		for_credit_per = (len(for_credit_atempted) / self.count_credit_students) * 100.0
		for_credit_per_s = '%0.1f' % for_credit_per
	else:
		for_credit_per_s = 'N/A'

	stat = _AssignmentStat( column.displayName, count,
							avg_grade_s, median_grade_s,
							std_grade_s, var_grade,
							per_attempted_s, for_credit_per_s )

	return stat

@view_config(context=ICourseInstance,
			 name=VIEW_COURSE_SUMMARY)
class CourseSummaryReportPdf(_AbstractReportView):

	report_title = _('Course Summary Report')

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
			accum = _TopCreators()
			accum.title = title
			accum.max_contributors = len(self.all_student_usernames)
			title_to_count[asm.ntiid] = accum

		for submission in qsets_by_student_in_course:
			asm = self_assessment_qsids[submission.questionSetId]
			title_to_count[asm.ntiid].incr_username(submission.creator)

		options['self_assessment_data'] = sorted(title_to_count.values(),
												 key=lambda x: x.title)

	def _build_engagement_data(self, options):
		md_catalog = self.md_catalog
		intersection = md_catalog.family.IF.intersection

		intids_of_notes = md_catalog['mimeType'].apply({'any_of': ('application/vnd.nextthought.note',)})
		intids_of_hls = md_catalog['mimeType'].apply({'any_of': ('application/vnd.nextthought.highlight',)})

		intids_of_notes = intersection( intids_of_notes,
										self.intids_created_by_students )
		intids_of_hls = intersection( intids_of_hls,
									  self.intids_created_by_students )

		all_notes = intids_of_notes
		all_hls = intids_of_hls

		lib = component.getUtility(IContentPackageLibrary)
		containers_in_course = lib.childrenOfNTIID(self.course.legacy_content_package.ntiid)
		# TODO: Is this getting everything? All the embedded containers, etc?
		containers_in_course = [x.ntiid for x in containers_in_course]

		intids_of_objects_in_course_containers = md_catalog['containerId'].apply({'any_of': containers_in_course})

		intids_of_notes = intersection( intids_of_notes,
										intids_of_objects_in_course_containers )
		intids_of_hls = intersection( intids_of_hls,
									  intids_of_objects_in_course_containers )

		data = dict()
		data['Notes'] = len(intids_of_notes)
		data['Highlights'] = len(intids_of_hls)
		data['Discussions'] = sum( (len(forum) for forum in self.course.Discussions.values()) )
		data['Discussion Comments'] = sum( (sum((len(topic) for topic in forum.values()))
											for forum in self.course.Discussions.values()) )

		options['engagement_data'] = sorted(data.items())

		outline = self.course.Outline
		def _recur(node, accum):
			ntiid = getattr(node, 'ContentNTIID', getattr(node, '_v_ContentNTIID', None))
			if ntiid:
				accum.add(ntiid)
			for n in node.values():
				_recur(n, accum)

		data = list()

		stat = namedtuple('Stat',
						  ('title', 'note_count', 'hl_count'))

		for unit in outline.values():
			for lesson in unit.values():
				ntiids = set()
				_recur(lesson, ntiids)
				for x in list(ntiids):
					try:
						kid = lib.pathToNTIID(x)[-1]
						ntiids.update( kid.embeddedContainerNTIIDs )
					except TypeError:
						pass

					for kid in lib.childrenOfNTIID(x):
						ntiids.add(kid.ntiid)
						ntiids.update(kid.embeddedContainerNTIIDs)
				ntiids.discard(None)
				local_notes = md_catalog['containerId'].apply({'any_of': ntiids})
				local_notes = intersection(local_notes, all_notes)
				local_hls = md_catalog['containerId'].apply({'any_of': ntiids})
				local_hls = intersection(local_hls, all_hls)

				data.append( stat( lesson.title, len(local_notes), len(local_hls)) )

		# Keep these in lesson order
		options['placed_engagement_data'] = data


	def _build_assignment_data(self, options):
		gradebook = IGradeBook(self.course)
		assignment_catalog = ICourseAssignmentCatalog(self.course)

		stats = list()
		for asg in assignment_catalog.iter_assignments():
			column = gradebook.getColumnForAssignmentId(asg.ntiid)
			stats.append(_assignment_stat_for_column(self, column))

		stats.sort(key=lambda x: x.title)
		options['assignment_data'] = stats

	def __call__(self):
		options = self.options
		self._build_engagement_data(options)
		self._build_enrollment_info(options)
		self._build_self_assessment_data(options)
		self._build_assignment_data(options)

		return options

from nti.app.assessment.interfaces import IUsersCourseAssignmentHistoryItem
from nti.assessment.interfaces import IQAssessedQuestionSet
from nti.assessment.interfaces import IQMultipleChoicePart
from nti.assessment.interfaces import IQMultipleChoiceMultipleAnswerPart
from nti.contentfragments.interfaces import IPlainTextContentFragment
from collections import Counter

@view_config(context=IGradeBookEntry,
			 name=VIEW_ASSIGNMENT_SUMMARY,
			 renderer="templates/AssignmentSummaryReport.rml")
class AssignmentSummaryReportPdf(_AbstractReportView):

	report_title = _('Assignment Summary Report')

	QuestionStat = namedtuple('QuestionStat',
							  ('title', 'content', 'avg_score',
							   'submission_counts',
							   ))

	def _build_assignment_data(self, options):
		stats = [_assignment_stat_for_column(self, self.context)]
		options['assignment_data'] = stats

	def _build_question_data(self, options):
		assignment = component.getUtility(IQAssignment, name=self.context.AssignmentId)

		ordered_questions = []
		qids_to_q = {}
		for apart in assignment.parts:
			for q in apart.question_set.questions:
				ordered_questions.append(q)
				qids_to_q[q.ntiid] = q

		column = self.context
		submissions = defaultdict(list)
		assessed_values = defaultdict(list)
		for grade in column.values():
			try:
				history = IUsersCourseAssignmentHistoryItem(grade)
			except TypeError: # Deleted user
				continue

			submission = history.Submission
			pending = history.pendingAssessment
			for set_submission in submission.parts:
				for question_submission in set_submission.questions:
					if len(question_submission.parts) != 1:
						continue
					question = qids_to_q[question_submission.questionId]
					question_part = question.parts[0]
					response = question_submission.parts[0]
					if (IQMultipleChoicePart.providedBy(question_part)
						and not IQMultipleChoiceMultipleAnswerPart.providedBy(question_part)
						and isinstance(response, int)):
						# convert int indexes into actual values; elide
						# the right answer so we only show incorrect answers
						__traceback_info__ = response
						if question_part.solutions[0].value == response:
							response = None
						else:
							response = question_part.choices[response]
							if isinstance(response, string_types):
								response = IPlainTextContentFragment(response)
					if response is not None:
						submissions[question_submission.questionId].append(response)

			for maybe_assessed in pending.parts:
				if not IQAssessedQuestionSet.providedBy(maybe_assessed):
					continue
				for assessed_question in maybe_assessed.questions:
					if len(assessed_question.parts) != 1:
						continue
					assessed_part = assessed_question.parts[0]
					assessed_values[assessed_question.questionId].append( assessed_part.assessedValue )

		options['xxx'] = submissions

		question_stats = []
		for i, q in enumerate(ordered_questions):
			assessed_value = assessed_values.get(q.ntiid, ())
			if assessed_value:
				avg_assessed = average(assessed_value)
				avg_assessed = avg_assessed * 100.0
				avg_assessed_s = '%0.1f' % avg_assessed
			else:
				avg_assessed_s = 'N/A'

			submission = submissions.get(q.ntiid, ())
			try:
				# If this gets big, we'll need to do something different,
				# like just showing top-answers
				# Arbitrary picking how many
				submission_counts = Counter(submission)
				if len(submission_counts) > 20:
					submission_counts = dict(submission_counts.most_common(20))
			except TypeError:
				# Dictionary or list submissions
				submission_counts = dict()

			title = i + 1
			content = IPlainTextContentFragment(q.content)
			if not content:
				content = IPlainTextContentFragment(q.parts[0].content)
			most_common_incorrect_response = ''
			most_common_correct_response = ''

			stat = self.QuestionStat(title, content, avg_assessed_s, submission_counts )
			question_stats.append(stat)

		options['question_stats'] = question_stats


	def __call__(self):
		options = self.options
		self._build_assignment_data(options)
		self._build_question_data(options)
		return options

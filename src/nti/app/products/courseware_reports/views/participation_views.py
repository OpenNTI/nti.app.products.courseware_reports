#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from .. import MessageFactory as _

import operator

from numbers import Number
from six import string_types
from collections import namedtuple
from collections import OrderedDict
from collections import defaultdict

from lxml import html

from zope import component

from pyramid.view import view_config
from pyramid.traversal import find_interface

from zope.catalog.catalog import ResultSet

from nti.app.assessment.interfaces import IUsersCourseAssignmentHistory

from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment

from nti.app.products.gradebook.interfaces import IGrade
from nti.app.products.gradebook.assignments import get_course_assignments

from nti.assessment.interfaces import IQAssignmentDateContext

from nti.contenttypes.courses.interfaces import ICourseEnrollments
from nti.contenttypes.courses.interfaces import	ICourseSubInstance

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import IDeletedObjectPlaceholder

from nti.dataserver.contenttypes.forums.interfaces import ITopic
from nti.dataserver.contenttypes.forums.interfaces import ICommunityBoard
from nti.dataserver.contenttypes.forums.interfaces import ICommunityForum
from nti.dataserver.contenttypes.forums.interfaces import IGeneralForumComment
from nti.dataserver.contenttypes.forums.interfaces import ICommunityHeadlineTopic

from nti.property.property import Lazy

from .. import VIEW_TOPIC_PARTICIPATION
from .. import VIEW_FORUM_PARTICIPATION
from .. import VIEW_STUDENT_PARTICIPATION

from ..decorators import course_from_forum

from ..reports import _TopCreators
from ..reports import _adjust_date
from ..reports import _common_buckets
from ..reports import _format_datetime
from ..reports import _build_buckets_options
from ..reports import _get_self_assessments_for_course

from . import CHART_COLORS
from . import FORUM_OBJECT_MIMETYPES

from .view_mixins import _AbstractReportView
from .view_mixins import _get_enrollment_scope_dict

class _AssignmentInfo(object):

	def __init__(self, title, submitted, submitted_late, grade_value, history, due_date):
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

	def _build_user_info(self, options):
		options['user'] = self.build_user_info(self.student_user)

	def _build_forum_data(self, options):
		course = self.course
		md_catalog = self.md_catalog
		uidutil = self.uidutil

		if ICourseSubInstance.providedBy(course):
			course_boards = (course.Discussions, course.__parent__.__parent__.Discussions)
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
													 uidutil)

		# Grab by course, ignore deleted comments and those before course start
		live_objects = self.filter_objects((x for x in forum_objects_created_by_student
											if find_interface(x, ICommunityBoard) in course_boards))

		# Group the forum objects by day and week
		time_buckets = _common_buckets(	live_objects,
										self,
										self.course_start_date)

		# Tabular breakdown of what topics the user created in what forum
		# and how many comments in which topics (could be bulkData or actual blockTable)
		topics_created = []
		comment_count_by_topic = defaultdict(int)
		for x in live_objects:
			if ITopic.providedBy(x):
				info = self.TopicCreated(x, x.title,
										 getattr(x.__parent__, 'title', None),
										 x.created)
				topics_created.append(info)
			elif IGeneralForumComment.providedBy(x):
				comment_count_by_topic[x.__parent__] += 1

		topics_created.sort(key=lambda x: (x.forum_name, x.topic_name))
		options['topics_created'] = topics_created
		options['total_forum_objects_created'] = len(live_objects)
		options['comment_count_by_topic'] = \
						sorted(comment_count_by_topic.items(),
							   key=lambda x: (getattr(x[0].__parent__, 'title', None), x[0].title))
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
		intids_of_submitted_qsets_by_student = md_catalog.family.IF.intersection(intids_of_submitted_qsets,
																				 self.intids_created_by_student)

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
			return getattr(qs.__parent__, 'title', None)

		for asm in self_assessments:
			title_to_count[_title_of_qs(asm)] = 0

		for submission in qsets_by_student_in_course:
			asm = self_assessment_qsids[submission.questionSetId]
			title_to_count[_title_of_qs(asm)] += 1

		options['self_assessment_title_to_count'] = sorted(title_to_count.items())

	def _build_assignment_data(self, options):
		assignment_catalog = get_course_assignments(self.course)
		histories = component.getMultiAdapter((self.course, self.student_user),
											  IUsersCourseAssignmentHistory)

		asg_data = list()
		date_context = IQAssignmentDateContext(self.course)

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
			due_date = date_context.of(assignment).available_for_submission_ending
			submitted_late = submitted > due_date if due_date and submitted else False

			asg_data.append(_AssignmentInfo(assignment.title, submitted,
											submitted_late,
											grade_value, history_item,
											due_date))

		# Sort null due_dates to end of result
		asg_data.sort(key=lambda x: (x.due_date is None, x.due_date, x.title))
		# Toggle timezones
		for x in asg_data:
			if x.due_date:
				x.due_date = _format_datetime(_adjust_date(x.due_date))
			if x.submitted:
				x.submitted = _format_datetime(_adjust_date(x.submitted))
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

	@Lazy
	def _only_course_enrollments( self ):
		enrollments = ICourseEnrollments( self.course )
		return {x.lower() for x in enrollments.iter_principals()}

	@Lazy
	def course(self):
		return self._course_from_forum(self.context)

	@Lazy
	def instructor_usernames(self):
		"All instructors from this instance and subinstances."
		# TODO: We may want to do this in other reports.
		result = {x.id.lower() for x in self.course.instructors}

		subinstances = self.course.SubInstances
		if subinstances:
			for subinstance in subinstances.values():
				subinstance_instr = {x.id.lower() for x in subinstance.instructors}
				result.update(subinstance_instr)
		return result

	def _get_comment_body(self, body):
		# Need to handle canvas, escape html, etc.
		# We also need to limit character count because of table/cell/page
		# constrains in pdf.
		try:
			result = ''.join(body)
			result = html.fromstring(result)
			result = result.text_content()
		except TypeError:
			# Not sure what else we could do with these
			result = '<Non-displayable>'

		if len(result) > COMMENT_MAX_LENGTH:
			result = result[:COMMENT_MAX_LENGTH] + '...[TRUNCATED]'
		return result

	def _get_user_scope_name(self, username):
		result = 'Public'
		if username.lower() in self.for_credit_student_usernames:
			result = 'ForCredit'
		return result

	def _get_comments_by_user(self, comments):
		"""
		Return a dict of username to ready-to-output comments.
		"""
		results = {}
		# Gather the comments per student username
		for comment in comments:
			creator_username = comment.creator.username
			if creator_username in self.instructor_usernames:
				continue
			# Build our parent comment data
			parent = getattr(comment, 'inReplyTo', None)
			parent_comment = None
			if IGeneralForumComment.providedBy(parent):
				scope_name = self._get_user_scope_name(parent.creator.username)
				parent_creator = self.build_user_info(parent.creator)
				parent_comment = _CommentInfo(parent_creator.username,
										parent_creator.display,
										_format_datetime(_adjust_date(parent.created)),
										_format_datetime(_adjust_date(parent.modified)),
										self._get_comment_body(parent.body),
										None,
										scope_name)
			# Now our comment
			scope_name = self._get_user_scope_name(creator_username)
			creator = self.build_user_info(creator_username)
			comment = _CommentInfo(creator.username,
									creator.display,
									_format_datetime(_adjust_date(comment.created)),
									_format_datetime(_adjust_date(comment.created)),
									self._get_comment_body(comment.body),
									parent_comment,
									scope_name)

			# Note the lower to match what we're doing with enrollments.
			results.setdefault(creator_username.lower(), []).append(comment)
		return results

	def _get_scope_user_dict_for_course(self, user_scope_dict, user_comment_dict):
		"""
		Returns a sorted dict of scopes to users to comments.
		"""
		scope_results = {}
		# Now populate those comments based on the enrollment scopes of those students.
		# This ensures we only get those students in our section.
		for scope_name in ('Public', 'ForCredit'):
			scope_students = user_scope_dict.get(scope_name)
			for username in scope_students:
				if username in user_comment_dict:
					scope_dict = scope_results.setdefault(scope_name, {})
					scope_dict[ self.build_user_info(username) ] = user_comment_dict[ username ]
			# Now sort by lower username
			scope_dict = scope_results.get(scope_name, None)
			if scope_dict is not None:
				scope_results[scope_name] = OrderedDict(
								sorted(scope_dict.items(),
										key=operator.itemgetter(1)))

		# Now build our sorted output
		# { ScopeName : { StudentInfo : (Comments) } }
		scope_results = OrderedDict(sorted(scope_results.items()))
		return scope_results

	def _get_section_scoped_comments(self, comments):
		"""
		Returns a sorted dict of sections to scoped-users to comments.
		"""
		results = {}
		user_comment_dict = self._get_comments_by_user(comments)
		super_scope_dict = self._get_enrollment_scope_dict

		# We want a map of course/section name to students enrolled in that section
		# Any top-level course will break down the results by section.
		# We should have section -> scope_name -> student comments.
		subinstances = self.course.SubInstances
		if subinstances:
			for subinstance_key, subinstance in subinstances.items():
				scope_dict = _get_enrollment_scope_dict(subinstance,
														set( subinstance.instructors ))
				user_comment_dict_by_scope = self._get_scope_user_dict_for_course(
													scope_dict, user_comment_dict)
				# Store with a displayable key
				results[ 'Section ' + subinstance_key ] = user_comment_dict_by_scope
			# We want to get a copy of our course enrollment scope. Since we're
			# grouping by subinstance, we want to explicitly exclude subinstance
			# enrollments from rolling up into our super course here.
			_new_dict = dict( super_scope_dict )
			for scope, users in super_scope_dict.items():
				_new_dict[scope] = users.intersection( self._only_course_enrollments )
			super_scope_dict = _new_dict


		user_comment_dict_by_scope = self._get_scope_user_dict_for_course(
											super_scope_dict, user_comment_dict)
		# Store with displayble name; useful for not accidentally
		# calling setNextTemplate with int-convertable index (e.g. '003' ).
		results[ self.course_name() ] = user_comment_dict_by_scope

		results = OrderedDict(sorted(results.items()))
		return results

	def _get_discussion_section_scoped_comments(self):
		"""
		Returns a sorted dict of discussion titles to section scoped comments.
		"""
		# Do we want zero counts?
		discussion_section_scoped = {}
		for topic in self.context.values():
			comments = (x for x in topic.values() if not IDeletedObjectPlaceholder.providedBy(x))
			section_scoped = self._get_section_scoped_comments( comments )
			discussion_section_scoped[topic.title] = section_scoped
		discussion_section_scoped = OrderedDict(sorted(discussion_section_scoped.items()))
		return discussion_section_scoped

	def _build_top_commenters(self, options):
		def _all_comments():
			for topic in self.context.values():
				# Should we use filter objects?
				for comment in topic.values():
					if not IDeletedObjectPlaceholder.providedBy(comment):
						yield comment
		buckets = _common_buckets(_all_comments(),
								  self,
								  self.course_start_date,
								  self.agg_creators)
		options['group_dates'] = buckets.group_dates
		options['top_commenters'] = buckets.top_creators
		options['top_commenters_colors'] = CHART_COLORS

		all_forum_stat = _build_buckets_options(options, buckets)
		options['all_forum_participation'] = all_forum_stat
		options['discussion_section_scope_comments'] = self._get_discussion_section_scoped_comments()

	def _build_comment_count_by_topic(self, options):
		comment_count_by_topic = list()
		top_creators = _TopCreators(self)

		for topic in self.context.values():
			comments = self.filter_objects(topic.values())

			count = len(comments)
			user_count = len({c.creator for c in comments})
			creator = self.build_user_info(topic.creator)
			created = topic.created
			comment_count_by_topic.append(self.TopicStats(topic.title, creator,
														created, count, user_count))

			top_creators.incr_username(topic.creator.username)

		comment_count_by_topic.sort(key=lambda x: (x.created, x.title))
		options['comment_count_by_topic'] = comment_count_by_topic
		if self.context:
			options['most_popular_topic'] = max(comment_count_by_topic, key=lambda x: x.comment_count)
			options['least_popular_topic'] = min(comment_count_by_topic, key=lambda x: x.comment_count)
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

		# Could probably break this into three parts if we want
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
			student_info = self.build_user_info(uname)
			stat = self.UserStats(student_info,
									creators.get(uname, 0),
									commenters.get(uname, 0),
									commenters.get_instructor_reply_count(uname, 0))
			user_stats.append(stat)
			if stat.total_comment_count == 1:
				only_one += 1
			if stat.total_comment_count > 0:
				unique_count += 1

		user_stats.sort()
		return (user_stats, only_one, unique_count)

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

	@Lazy
	def course(self):
		return self._course_from_forum(self.context.__parent__)

	def _build_top_commenters(self, options):
		live_objects = self.filter_objects(self.context.values())
		buckets = _common_buckets(live_objects,
									self,
									self.course_start_date)

		options['section_scoped_comments'] = self._get_section_scoped_comments(live_objects)
		options['top_commenters'] = buckets.top_creators
		options['group_dates'] = buckets.group_dates
		options['top_commenters_colors'] = CHART_COLORS
		all_forum_stat = _build_buckets_options(options, buckets)
		options['all_forum_participation'] = all_forum_stat

	def _build_topic_info(self):
		topic_name = self.context.title
		forum_name = self.context.__parent__.title
		return _TopicInfo(topic_name, forum_name)

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
		options['top_creators'] = _TopCreators(self)
		options['topic_info'] = self._build_topic_info()
		self._build_user_stats(options)
		return options

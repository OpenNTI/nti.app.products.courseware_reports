#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
$Id$
"""
from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import component

from itertools import groupby
from collections import namedtuple
from collections import defaultdict
from datetime import datetime

import BTrees
from pyramid.view import view_config
from pyramid.traversal import find_interface

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
from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment
from nti.app.products.gradebook.interfaces import IGrade
from nti.dataserver.interfaces import IUser

from nti.dataserver.contenttypes.forums.interfaces import ICommunityBoard
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

@view_config(route_name='objects.generic.traversal',
			 context=ICourseInstanceEnrollment,
			 request_method='GET',
			 permission=ACT_READ,
			 name='StudentParticipationReport.pdf',
			 renderer="templates/StudentParticipationReport.rml")
class StudentParticipationReportPdf(AbstractAuthenticatedView):

	FORUM_OBJECT_MIMETYPES = ['application/vnd.nextthought.forums.generalforumcomment',
							  'application/vnd.nextthought.forums.communityforumcomment',
							  'application/vnd.nextthought.forums.communitytopic']

	TopicCreated = namedtuple('TopicCreated',
							  ('topic', 'topic_name', 'forum_name', 'created'))
	AssignmentInfo = namedtuple('AssignmentInfo',
								('title', 'submitted', 'grade_value'))

	@Lazy
	def course(self):
		return ICourseInstance(self.context)
	@Lazy
	def student_user(self):
		return IUser(self.context)
	@Lazy
	def md_catalog(self):
		return component.getUtility(ICatalog,CATALOG_NAME)
	@Lazy
	def uidutil(self):
		return component.getUtility(IIntIds)
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
		intids_of_forum_objects = md_catalog['mimeType'].apply({'any_of': self.FORUM_OBJECT_MIMETYPES})
		# We could apply based on createdTime to be no less than the start time of the
		# course
		intids_of_forum_objects_created_by_student = md_catalog.family.IF.intersection(intids_created_by_student, intids_of_forum_objects)
		forum_objects_created_by_student = ResultSet(intids_of_forum_objects_created_by_student,
													 uidutil )
		forum_objects_created_by_student_in_course = [x for x in forum_objects_created_by_student
													  if find_interface(x, ICommunityBoard) == course_board]
		# Group the forum objects by day
		day_normalizer = TimestampNormalizer(TimestampNormalizer.RES_DAY)
		day_key = lambda x: int(day_normalizer.value(x.createdTime))
		forum_objects_created_by_student_in_course.sort(key=day_key)

		forum_objects_by_day = BTrees.family64.II.BTree()
		forum_objects_by_week_number = BTrees.family64.II.BTree()
		for k, g in groupby(forum_objects_created_by_student_in_course, day_key):
			count = len(list(g))
			forum_objects_by_day[k] = count

			week_num = datetime.utcfromtimestamp(k).isocalendar()[1]
			if week_num in forum_objects_by_week_number:
				forum_objects_by_week_number[week_num] += count
			else:
				forum_objects_by_week_number[week_num] = count

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
		options['forum_objects_by_day'] = forum_objects_by_day
		options['forum_objects_by_week_number'] = forum_objects_by_week_number

		def as_series():
			rows = ['%d    %d' % (k,forum_objects_by_week_number.get(k, 0))
					for k in range(forum_objects_by_week_number.minKey() - 1,
								   forum_objects_by_week_number.maxKey() + 1)]
			return '\n'.join(rows)
		options['forum_objects_by_week_number_series'] = as_series
		options['forum_objects_by_week_number_max'] = max(forum_objects_by_week_number.values()) + 1
		options['forum_objects_by_week_number_value_min'] = forum_objects_by_week_number.minKey() - 1
		options['forum_objects_by_week_number_value_max'] = forum_objects_by_week_number.maxKey() + 1

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
				submitted = history_item.created
			else:
				grade_value = ''
				submitted = ''
			asg_data.append(self.AssignmentInfo(assignment.title, submitted, grade_value))

		asg_data.sort(key=lambda x: x.title)
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
		options = dict()
		self._build_forum_data(options)

		# Each self-assessment and how many times taken (again bulkData)
		self._build_self_assessment_data(options)

		# Table of assignment history and grades for all assignments in course
		self._build_assignment_data(options)

		return options

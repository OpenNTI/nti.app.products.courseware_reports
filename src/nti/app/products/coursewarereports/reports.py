#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""
from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import heapq
from itertools import groupby
from datetime import datetime
from datetime import timedelta
from collections import namedtuple

import pytz
import BTrees

from numpy import std
from numpy import median
from numpy import asarray
from numpy import average
from numbers import Number

from nti.app.assessment.interfaces import ICourseAssessmentItemCatalog

from nti.assessment.interfaces import IQAssignment
from nti.assessment.interfaces import IQuestionSet

from nti.contentfragments.interfaces import IPlainTextContentFragment

# XXX: Fix a unicode decode issue.
# TODO: Make this a formal patch
import reportlab.platypus.paragraph
_reportlab_paragraph = reportlab.platypus.paragraph

family64 = BTrees.family64

class _SplitText(unicode):
	pass
reportlab.platypus.paragraph._SplitText = _SplitText

def _adjust_timestamp( timestamp ):
	"""Takes a timestamp and returns a timezoned datetime"""
	date = datetime.utcfromtimestamp( timestamp ) 
	return _adjust_date( date )

def _adjust_date( date ):
	"""Takes a date and returns a timezoned datetime"""
	#TODO Hard code everything to CST for now
	utc_date = pytz.utc.localize( date )
	cst_tz = pytz.timezone('US/Central')
	return utc_date.astimezone( cst_tz )

def _format_datetime( local_date ):
	"""Returns a string formatted datetime object"""
	return local_date.strftime("%Y-%m-%d %H:%M")

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
					  ('count_by_day', 'count_by_week_number', 'top_creators', 'group_dates'))

class _StudentInfo( namedtuple( '_StudentInfo', 
								('display', 'username', 'count', 'perc' ))):
	"""Holds general student info. 'count' and 'perc' are optional values"""
	def __new__( self, display, username, count=None, perc=None ):
		return super(_StudentInfo,self).__new__( self,display,username,count,perc )

class _TopCreators(object):
	"""Accumulate stats in three parts: for credit students, tourists, and aggregate"""

	family = BTrees.family64
	total = 0
	title = ''
	max_contributors = None
	aggregate_creators = None
	aggregate_remainder = None
	max_contributors_for_credit = None
	max_contributors_non_credit = None

	def __init__(self, report):
		self._data = self.family.OI.BTree()
		self._get_student_info = report.get_student_info
		self.max_contributors = report.count_all_students
		self._non_credit_students = report.open_student_usernames
		self.max_contributors_for_credit = report.count_credit_students
		self.max_contributors_non_credit = report.count_non_credit_students
		self._for_credit_students = report.for_credit_student_usernames

	@property
	def _for_credit_data(self):
		return {username: i for username, i in self._data.items() if username.lower() in self._for_credit_students}

	@property
	def _non_credit_data(self):
		return {username: i for username, i in self._data.items() if username.lower() in self._non_credit_students}

	def _get_largest(self):
		return self._do_get_largest(self._data, self.total)

	def _get_for_credit_largest(self):
		return self._do_get_largest(self._for_credit_data, self.for_credit_total)

	def _build_student_info(self,stat):
		student_info = self._get_student_info( stat[0] )
		count = stat[1]
		perc = ( count / self.total * 100 ) if self.total else 0.0
		return _StudentInfo( 	student_info.display,
								student_info.username,
								count, perc )

	def _do_get_largest(self,data,total_to_change):
		# Returns the top commenter names, up to (arbitrarily) 10
		# of them, with the next being 'everyone else'
		largest = heapq.nlargest(10, data.items(), key=lambda x: x[1])
		
		largest = [ self._build_student_info(x) for x in largest ]
		
		#Get aggregate remainder
		if len(data) > len(largest):
			largest_total = sum( (x.count for x in largest) )
			remainder = total_to_change - largest_total
			# TODO: Localize and map this
			percent = (remainder / total_to_change) * 100
			self.aggregate_remainder = _StudentInfo( 'Others', 'Others', largest_total, percent )
		return largest

	def __iter__(self):
		return iter(self._get_largest())

	def __bool__(self):
		return bool(self._data)
	__nonzero__ = __bool__

	def series(self):
		return ' '.join( ('%d' % x.count for x in self._get_largest() ) )

	@property
	def unique_contributors(self):
		return len(self.keys())
		
	@property
	def unique_contributors_for_credit(self):
		return len(self.for_credit_keys())
	
	@property
	def unique_contributors_non_credit(self):
		return len(self.non_credit_keys())

	@property
	def for_credit_total(self):
		data = self._for_credit_data
		if data:
			return sum(data.values())
		return 0

	@property
	def non_credit_total(self):
		data = self._non_credit_data
		if data:
			return sum(data.values())
		return 0

	def incr_username(self, username):
		self.total += 1

		if username in self._data:
			self._data[username] += 1
		else:
			self._data[username] = 1
			
		if self.aggregate_creators is not None:
			self.aggregate_creators.incr_username( username )	

	def keys(self):
		return self._data.keys()
	
	def for_credit_keys(self):
		return self._for_credit_data.keys()
	
	def non_credit_keys(self):
		return self._non_credit_data.keys()

	def get(self, key, default=None):
		return self._data.get(key, default)

	def average_count(self):
		if self.total:
			return self.total / len(self._data)
		return 0

	def average_count_str(self):
		return "%0.1f" % self.average_count()

	def percent_contributed(self, contributors_total, contributors_count):
		if not contributors_total:
			return 100
		return (contributors_count / contributors_total) * 100.0

	def percent_contributed_str(self):
		return "%0.1f" % self.percent_contributed( self.max_contributors, self.unique_contributors )

	def for_credit_percent_contributed_str(self):
		return "%0.1f" % self.percent_contributed( self.max_contributors_for_credit, self.unique_contributors_for_credit )

	def non_credit_percent_contributed_str(self):
		return "%0.1f" % self.percent_contributed( self.max_contributors_non_credit, self.unique_contributors_non_credit )

class _DateCategoryAccum(object):
	"""	Will accumulate 'date' objects based on inbound dates and return a week number.
		The date inputs *must* be in sorted order. Otherwise, our behavior is undefined."""
	
	def __init__( self, start_date ):
		self.dates = []
		self.old_week_num = None
		
		start_date = start_date.date()
		self.start_monday = start_date - timedelta( days=start_date.weekday() )

	def accum_all( self, dates ):
		"""Given a list of sorted dates, accumulate them"""
		for d in dates:
			self.accum( d )
		return self.get_dates()

	def accum( self, input_date ):
		group_monday = input_date - timedelta( days=input_date.weekday() )
		week_num = ( (group_monday - self.start_monday).days // 7 )
		
		if self.old_week_num is None:
			self.old_week_num = week_num
			self.dates.append( group_monday )
		
		if week_num != self.old_week_num:
			#Check for week gaps and fill
			for f in range(self.old_week_num - week_num + 1, 0):
				#Add negative weeks to retain order
				old_monday = group_monday + timedelta( weeks=1 * f )
				self.dates.append( old_monday )
			self.dates.append( group_monday )
			self.old_week_num = week_num
			
		return week_num

	def get_dates( self ):
		return self.dates

class _AnswerStat(object):
	"""Holds stat and display information for a particular answer."""
	def __init__(self, answer, is_correct):
		self.answer = answer
		self.is_correct = is_correct
		self.count = 1
		self.perc_s = None
		self.letter_prefix = None

def _common_buckets( objects,report,object_create_date,agg_creators=None ):
	"""
	Given a list of :class:`ICreated` objects,
	return a :class:`_CommonBuckets` containing three members:
	a map from a normalized timestamp for each day to the number of
	objects created that day, and a map from an ISO week number
	to the number of objects created that week,
	and an instance of :class:`_TopCreators`.

	The argument can be an iterable sequence, we sort a copy.

	"""
	# We are not converting these to our timezone.  Since we're 
	# bucketing by weeks, fine-grained timezone adjustments
	# are not likely to be worthwhile. 
	day_key = lambda x: x.created.date()
	objects = sorted(objects, key=day_key)
	date_accum = _DateCategoryAccum( object_create_date )

	forum_objects_by_day = []
	forum_objects_by_week_number = family64.II.BTree()
	top_creators = _TopCreators( report )
	top_creators.aggregate_creators = agg_creators

	for k, g in groupby(objects, day_key):
		group = list(g)
		count = len(group)
		for o in group:
			top_creators.incr_username(o.creator.username)

		week_num = date_accum.accum( k )

		if week_num in forum_objects_by_week_number:
			forum_objects_by_week_number[week_num] += count
		else:
			forum_objects_by_week_number[week_num] = count

	dates = date_accum.get_dates()
	
	return _CommonBuckets(forum_objects_by_day, forum_objects_by_week_number, top_creators, dates)

ForumObjectsStat = namedtuple('ForumObjectsStat',
							  ('forum_objects_by_day', 'forum_objects_by_week_number',
							   'forum_objects_by_week_number_series', 'forum_objects_by_week_number_max',
							   'forum_objects_by_week_number_value_min', 'forum_objects_by_week_number_value_max',
							   'forum_objects_by_week_number_categories',
							   'forum_objects_by_week_number_y_step'))

def _build_buckets_options(options, buckets):
	forum_objects_by_week_number = buckets.count_by_week_number
	forum_objects_by_day = buckets.count_by_day

	options['forum_objects_by_day'] = forum_objects_by_day
	options['forum_objects_by_week_number'] = forum_objects_by_week_number

	if forum_objects_by_week_number:

		minKey = forum_objects_by_week_number.minKey()
		maxKey = forum_objects_by_week_number.maxKey()
		full_range = range(minKey, maxKey + 1)

		def as_series():
			rows = ['%d' % forum_objects_by_week_number.get(k, 0)
					for k in full_range]
			return '\n'.join(rows)

		options['forum_objects_by_week_number_series'] = as_series
		options['forum_objects_by_week_number_max'] = _max = max(forum_objects_by_week_number.values()) + 1
		options['forum_objects_by_week_number_value_min'] = minKey - 1
		options['forum_objects_by_week_number_value_max'] = maxKey + 1

		#If we have few values, specify our step size; otherwise, let the chart do the work.
		if _max < 10:
			options['forum_objects_by_week_number_y_step'] = 1

		weeks_s = []
		if len( buckets.group_dates ) < 13:
			for d_entry in buckets.group_dates:
				weeks_s.append( d_entry.strftime( '%b %d' ) )
		else:
			for d_entry in buckets.group_dates:
				weeks_s.append( d_entry.strftime( '%m-%d' ) )

		options['forum_objects_by_week_number_categories'] = weeks_s
	else:
		options['forum_objects_by_week_number_series'] = ''
		options['forum_objects_by_week_number_max'] = 0
		options['forum_objects_by_week_number_value_min'] = 0
		options['forum_objects_by_week_number_value_max'] = 0
		options['forum_objects_by_week_number_categories'] = ''

	return ForumObjectsStat( *[options.get(x)
							   for x in ForumObjectsStat._fields] )

_AssignmentStat = namedtuple('_AssignmentStat',
							 ('title', 'count', 'due_date',
							  'total', 'for_credit_total',
							  'non_credit_total',
							  'avg_grade', 'for_credit_avg_grade',
							  'non_credit_avg_grade', 'median_grade', 'std_dev_grade',
							  'attempted_perc', 'for_credit_attempted_perc', 'non_credit_attempted_perc' ))

def _assignment_stat_for_column(report, column, filter=None):
	count = len(column)

	for_credit_keys = report.for_credit_student_usernames
	non_credit_keys = report.open_student_usernames
	for_credit_grade_points = list()
	non_credit_grade_points = list()
	all_grade_points = list()
	for_credit_total = non_credit_total = 0

	for username, grade in column.items():
		username = username.lower()
		#Skip if not in filter
		if filter is not None and username not in filter:
			continue
		
		grade_val = None
		# We could have values (19.3), combinations (19.3 A), or strings ('GR'); 
		# Count the latter case and move on
		if grade.value is not None:
			try:
				if isinstance(grade.value, Number):
					grade_val = grade.value
				elif len( grade.value.split() ) > 1:
					grade_val = float( grade.value.split()[0] )
			except ValueError:
				pass
		
		# We still increase count of attempts, even if the assignment is ungraded.
		# We skip any non credit/non-credit students, which should be any
		# instructors or dropped students.
		if username in for_credit_keys:
			for_credit_total += 1
			if grade_val is not None:
				all_grade_points.append( grade_val )
				for_credit_grade_points.append( grade_val )
		elif username in non_credit_keys:
			non_credit_total += 1
			if grade_val is not None:
				all_grade_points.append( grade_val )
				non_credit_grade_points.append( grade_val )

	total = for_credit_total + non_credit_total

	for_credit_grade_points = asarray(for_credit_grade_points)
	non_credit_grade_points = asarray(non_credit_grade_points)
	all_grade_points = asarray(all_grade_points)

	# Credit
	if for_credit_grade_points.any():
		for_credit_avg_grade = average(for_credit_grade_points)
		for_credit_avg_grade_s = '%0.1f' % for_credit_avg_grade
	else:
		for_credit_avg_grade_s = 'N/A'

	# Non-credit
	if non_credit_grade_points.any():
		non_credit_avg_grade = average(non_credit_grade_points)
		non_credit_avg_grade_s = '%0.1f' % non_credit_avg_grade
	else:
		non_credit_avg_grade_s = 'N/A'

	# Aggregate
	if for_credit_grade_points.any() and non_credit_grade_points.any():
		agg_array = all_grade_points
		agg_avg_grade = average(agg_array)
		avg_grade_s = '%0.1f' % agg_avg_grade
		median_grade = median(agg_array)
		std_dev_grade = std(agg_array)
	elif for_credit_grade_points.any():
		avg_grade_s = for_credit_avg_grade_s
		median_grade = median(for_credit_grade_points)
		std_dev_grade = std(for_credit_grade_points)
	elif non_credit_grade_points.any():
		avg_grade_s = non_credit_avg_grade_s
		median_grade = median(non_credit_grade_points)
		std_dev_grade = std(non_credit_grade_points)
	else:
		avg_grade_s = 'N/A'
		median_grade = std_dev_grade = 0

	median_grade_s = '%0.1f' % median_grade
	std_dev_grade_s = '%0.1f' % std_dev_grade

	if report.count_all_students:
		per_attempted = (count / report.count_all_students) * 100.0
		per_attempted_s = '%0.1f' % per_attempted
	else:
		per_attempted_s = 'N/A'

	if report.count_credit_students:
		for_credit_per = (for_credit_total / report.count_credit_students) * 100.0
		for_credit_per_s = '%0.1f' % for_credit_per
	else:
		for_credit_per_s = 'N/A'
		
	if report.count_non_credit_students:
		non_credit_per = (non_credit_total / report.count_non_credit_students) * 100.0
		non_credit_per_s = '%0.1f' % non_credit_per
	else:
		non_credit_per_s = 'N/A'

	stat = _AssignmentStat( column.displayName, count, column.DueDate, total,
							for_credit_total, non_credit_total,
							avg_grade_s, for_credit_avg_grade_s,
							non_credit_avg_grade_s,
							median_grade_s,	std_dev_grade_s,
							per_attempted_s, for_credit_per_s, non_credit_per_s )

	return stat	

class _QuestionPartStat(object):
	"""Holds stat and display information for a particular question part."""
	def __init__(self, letter_prefix, answer_stats=None, avg_score=0):
		self.answer_stats = answer_stats if answer_stats is not None else {}
		self.letter_prefix = letter_prefix
		self.avg_score = avg_score
		self.assessed_values = []

class _QuestionStat(object):
	"""Holds stat and display information for a particular question."""
	def __init__(self, question_part_stats, title=None, content=None, avg_score=0, submission_count=0 ):
		self.question_part_stats = question_part_stats
		self.submission_count = submission_count
		self.title = title
		self.content = content
		self.avg_score = avg_score

def _build_question_stats( ordered_questions, question_stats ):
	"""From questions_stats, return fully formed question_stat objects"""
	results = []
	for i, q in enumerate( ordered_questions ):
		q_stat = question_stats.get( q.ntiid )
		question_part_stats = q_stat.question_part_stats if q_stat else {}
		total_submits = q_stat.submission_count if q_stat else 0
		
		question_parts = []
		question_part_grades = []
		
		#Go through each question part
		for question_part_stat in question_part_stats.values():
			#Do we have an unassessed question?
			avg_assessed_s = 'N/A'
			if question_part_stat.assessed_values:
				avg_assessed = average( question_part_stat.assessed_values )
				avg_assessed = avg_assessed * 100.0
				avg_assessed_s = '%0.1f' % avg_assessed
				
				question_part_grades.append( avg_assessed )

			# We may want to display *all* of the available multiple choice answers. If so, this is the place.
			top_answer_stats = _get_top_answers( question_part_stat.answer_stats )
			_finalize_answer_stats( top_answer_stats, total_submits )
			
			question_parts.append( _QuestionPartStat( 	question_part_stat.letter_prefix, 
														top_answer_stats, 
														avg_assessed_s ) )

		title = i + 1
		content = IPlainTextContentFragment( q.content )
		if not content:
			content = IPlainTextContentFragment( q.parts[0].content )

		#Averaging all the parts to get the question assessment grade
		question_avg_assessed_s = '%0.1f' % average( question_part_grades ) if question_part_grades else 'N/A'

		stat = _QuestionStat( question_parts, title, content, question_avg_assessed_s )
		results.append( stat )
			
	return results

def _get_top_answers( answer_stats ):
	# Arbitrarily picking how many to trim our list down to.
	# 	->8 since it fits on page with header, currently.
	# We order by popularity; we could do by content perhaps.
	top_answer_stats = heapq.nlargest( 8, answer_stats.values(), key=lambda x: x.count )
	
	if len( answer_stats.values() ) > len( top_answer_stats ):
		missing_corrects = [x for x in answer_stats.values() 
							if x.is_correct and x not in top_answer_stats]
		if missing_corrects:
			# Ok, our correct answer(s) isn't in our trimmed-down set; make it so.
			# Maybe we should be more pragmatic here to make sure we aren't losing 
			# relevant information.
			top_answer_stats = top_answer_stats[:-1 * len(missing_corrects)] + missing_corrects
	return top_answer_stats

def _finalize_answer_stats( answer_stats, total_submits ):
	"""Modifies the incoming answer_stats with relevant values"""
	# Now update the letter and perc values for our answer_stats
	#letters = string.ascii_uppercase
	for j in range( len( answer_stats ) ):
		sub = answer_stats[j]
		#sub.letter_prefix = letters[j]
		sub.letter_prefix = str( j + 1 )
		sub.perc_s = '%0.1f' % ( sub.count * 100.0 / total_submits ) if total_submits else 'N/A'


from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

#disable: accessing protected members, too many methods
#pylint: disable=W0212,R0904

import unittest

from ..reports import _format_datetime
from ..reports import _adjust_timestamp
from ..reports import _adjust_date
from ..reports import _TopCreators
from ..reports import _StudentInfo
from ..reports import _common_buckets
from ..reports import _build_buckets_options
from ..reports import _get_top_answers
from ..reports import _finalize_answer_stats
from ..reports import _build_question_stats
from ..reports import _assignment_stat_for_column
from ..reports import _AssignmentStat
from ..reports import _QuestionPartStat
from ..reports import _QuestionStat
from ..reports import _DateCategoryAccum

from ..views import _AnswerStat

from nti.contentfragments.interfaces import PlainTextContentFragment

from collections import namedtuple

from datetime import datetime

from six import string_types

import time

from hamcrest import assert_that
from hamcrest import not_none
from hamcrest import none
from hamcrest import empty
from hamcrest import equal_to
from hamcrest import has_property
from hamcrest import has_length
from hamcrest import contains_string
from hamcrest import only_contains
from hamcrest import greater_than_or_equal_to
from hamcrest import greater_than
from hamcrest import less_than
from hamcrest import less_than_or_equal_to
from hamcrest import close_to
from hamcrest import is_
from hamcrest import is_in
from hamcrest import is_not
from hamcrest import contains

class TestReports( unittest.TestCase ):

	def test_format_date( self ):
		time = datetime.now()
		assert_that( _format_datetime( time ), not_none() )
		
	def test_adjust_timestamp(self):
		ts = int(time.time())
		adjusted = _adjust_timestamp( ts )
		assert_that( adjusted, not_none() )
		assert_that( adjusted.tzname(), not_none() )
		
	def test_adjust_date(self):
		d = datetime.now()	
		adjusted = _adjust_date( d )
		assert_that( adjusted, not_none() )
		assert_that( adjusted.tzname(), not_none() )
		
	def test_finalize_answer_stats(self):
		_finalize_answer_stats( [], 4 )	
		
		answers = [ _AnswerStat( 'bleh', False ) ]
		_finalize_answer_stats( answers, 0 )	
		assert_that( answers[0].letter_prefix, not_none() )
		assert_that( answers[0].perc_s, not_none() )
		
		answers = [ _AnswerStat( 'bleh', False ), 
					_AnswerStat( 'bleh', False ),
					_AnswerStat( 'bleh', False ),
					_AnswerStat( 'bleh', False ) ]
		_finalize_answer_stats( answers, 4 )
		for a in answers:
			assert_that( a.letter_prefix, not_none() )
			assert_that( a.perc_s, equal_to( '25.0%' ) )
	
	def test_get_top_answers(self):
		results = _get_top_answers( {} )	
		assert_that( results, not_none() )
		assert_that( results, has_length( 0 ) )
		
		answers = { 'bleh':_AnswerStat( 'bleh', False ) }
		results = _get_top_answers( answers )	
		
		assert_that( results, not_none() )
		assert_that( results, has_length( 1 ) )
		
		#9 stats
		stat1 = _AnswerStat( 'key1', False ); stat1.count = 7
		stat2 = _AnswerStat( 'key2', False ); stat2.count = 3
		stat3 = _AnswerStat( 'key3', False ); stat3.count = 5 
		stat4 = _AnswerStat( 'key4', False ); stat4.count = 6 
		stat5 = _AnswerStat( 'key5', False ); stat5.count = 6 
		stat6 = _AnswerStat( 'key6', False ); stat6.count = 9 
		stat7 = _AnswerStat( 'key7', False ); stat7.count = 8 
		stat8 = _AnswerStat( 'key8', False ); stat8.count = 4 
		stat9 = _AnswerStat( 'key9', True ) 
		answers = { stat1.answer: stat1, 
					stat2.answer: stat2,
					stat3.answer: stat3,
					stat4.answer: stat4,
					stat5.answer: stat5,
					stat6.answer: stat6,
					stat7.answer: stat7,
					stat8.answer: stat8,
					stat9.answer: stat9 }
		results = _get_top_answers( answers )	
		
		assert_that( results, not_none() )
		assert_that( results, has_length( 8 ) )
		assert_that( results[0].answer, equal_to( 'key6' ) )
		
		assert_that( stat9, is_in( results ) )
		assert_that( stat2, is_not( is_in( results ) ) ) 
		
		corrects = [ x for x in results if x.is_correct ]
		assert_that( corrects, not_none() )
		assert_that( corrects, has_length( 1 ) )
		assert_that( corrects, only_contains( stat9 ) )

_quests = namedtuple( '_quests', ( 'ntiid', 'content' ))
_q_stats = namedtuple( 'q_stats', ( 'question_part_stats', 'submission_count' ) )
	
class TestBuildQuestions( unittest.TestCase ):
	
	def test_empty(self):
		results = _build_question_stats( [], None )
		assert_that( results, not_none() )
	
	def test_single(self):
		q1s = _quests( 1, PlainTextContentFragment( 'content1' ) )
		
		results = _build_question_stats( [q1s], {} )
		
		assert_that( results, not_none() )
		assert_that( results, has_length( 1 ) )
		assert_that( results[0].question_part_stats, not_none() )
		assert_that( results[0].avg_score, not_none() )
		assert_that( isinstance( results[0].avg_score, string_types ) )
		
	def test_multi(self):
		q1s = _quests( 1, PlainTextContentFragment( 'content1' ) )
		q2s = _quests( 2, PlainTextContentFragment( 'content2' ) )
		
		results = _build_question_stats( [q1s,q2s], {} )
		
		assert_that( results, not_none() )
		assert_that( results, has_length( 2 ) )
		assert_that( results[0].question_part_stats, not_none() )
		assert_that( results[0].avg_score, not_none() )
		assert_that( isinstance( results[0].avg_score, string_types ) )	
		
	def test_single_with_stats(self):
		q1s = _quests( 1, PlainTextContentFragment( 'content1' ) )
		
		results = _build_question_stats( [q1s], {1:_QuestionStat( {} ) } )
		
		#Empty stat
		assert_that( results, not_none() )
		assert_that( results, has_length( 1 ) )
		assert_that( results[0].question_part_stats, not_none() )
		assert_that( results[0].avg_score, is_('N/A') )
		assert_that( isinstance( results[0].avg_score, string_types ) )
		
		#Stat with no assessments
		q_part_stat = _QuestionPartStat( 'I' )
		q_part_stat.assessed_values = []
		q_stat = _QuestionStat( {1:q_part_stat})
		results = _build_question_stats( [q1s], {1:q_stat} )
		
		assert_that( results, not_none() )
		assert_that( results, has_length( 1 ) )
		assert_that( results[0].question_part_stats, has_length( 1 ) )
		assert_that( results[0].avg_score, is_('N/A') )
		assert_that( results[0].question_part_stats[0].avg_score, is_( 'N/A' ) )
		
		#Stat with assessments and answers
		stat1 = _AnswerStat( 'key1', False ); stat1.count = 5
		stat2 = _AnswerStat( 'key2', True ); stat2.count = 3
		stat3 = _AnswerStat( 'key3', True ); stat3.count = 7 
		answers = { stat1.answer: stat1, 
					stat2.answer: stat2,
					stat3.answer: stat3 }
		
		q_part_stat = _QuestionPartStat( 'I', answers )
		q_part_stat.assessed_values = [ 0, 1.0 ]
		q_stat = _QuestionStat( {1:q_part_stat} )
		results = _build_question_stats( [q1s], {1:q_stat} )
		
		assert_that( results, not_none() )
		assert_that( results, has_length( 1 ) )
		assert_that( results[0].avg_score, is_('50.0') )
		assert_that( results[0].question_part_stats, has_length( 1 ) )
		assert_that( results[0].question_part_stats[0].avg_score, is_( '50.0' ) )
		
		q_part_ordered_answer_stats = results[0].question_part_stats[0].answer_stats
		assert_that( q_part_ordered_answer_stats, has_length( 3 )  )
		assert_that( q_part_ordered_answer_stats, contains( stat3, stat1, stat2 )  )
		
	def test_multi_with_stats(self):
		q1s = _quests( 1, PlainTextContentFragment( 'content1' ) )
		q2s = _quests( 2, PlainTextContentFragment( 'content2' ) )
		
		#Multi-questions/multi-parts
		#Question One
		q_part_stat = _QuestionPartStat( 'I' )
		q_part_stat.assessed_values = [ 0, 1.0 ]
		q_part_stat2 = _QuestionPartStat( 'II' )
		q_part_stat2.assessed_values = [ 1.0, 1.0 ]
		q_stat = _QuestionStat( {1:q_part_stat, 2:q_part_stat2} )
		
		#Question Two
		q_part_stat = _QuestionPartStat( 'II' )
		q_part_stat.assessed_values = [ 1.0 ]
		q_stat2 = _QuestionStat( {1:q_part_stat} )
		
		results = _build_question_stats( [q1s,q2s], {1:q_stat, 2:q_stat2} )
		
		assert_that( results, not_none() )
		assert_that( results, has_length( 2 ) )
		assert_that( results[0].question_part_stats, has_length( 2 ) )
		assert_that( results[0].question_part_stats[0].avg_score, is_( '50.0' ) )
		assert_that( results[0].question_part_stats[1].avg_score, is_( '100.0' ) )
		assert_that( results[0].avg_score, id( '75.0' ) )
		assert_that( results[1].avg_score, id( '100.0' ) )


class TestDateAccum( unittest.TestCase ):
		
	def test_date_accum_empty(self):
		start_date = datetime( year=2014, month=4, day=5, hour=0, minute=30 )
		date_accum = _DateCategoryAccum( start_date )
		date_accum.accum_all( [] )
		dates = date_accum.get_dates()
		
		assert_that( dates, not_none() )
		assert_that( dates, has_length( 0 ) )
		
	def test_date_accum(self):
		# Five different weeks with values over a five week window
		#Week1
		d1 = datetime( year=2014, month=3, day=28, hour=0, minute=30 ).date()
		#Week2, seven total
		d2 = datetime( year=2014, month=4, day=1, hour=0, minute=30 ).date()
		d3 = datetime( year=2014, month=4, day=2, hour=0, minute=30 ).date()
		d4 = datetime( year=2014, month=4, day=3, hour=0, minute=30 ).date()
		d5 = datetime( year=2014, month=4, day=4, hour=0, minute=30 ).date()
		d6 = datetime( year=2014, month=4, day=5, hour=0, minute=30 ).date()
		d7 = datetime( year=2014, month=4, day=5, hour=0, minute=30 ).date()
		d8 = datetime( year=2014, month=4, day=5, hour=0, minute=30 ).date()
		#Week3
		d9 = datetime( year=2014, month=4, day=9, hour=0, minute=30 ).date()
		#Week4
		#Week5
		d10 = datetime( year=2014, month=4, day=27, hour=0, minute=30 ).date()
		input_dates = [d1,d2,d3,d4,d5,d6,d7,d8,d9,d10]
		
		start_date = datetime( year=2014, month=4, day=5, hour=0, minute=30 )
		date_accum = _DateCategoryAccum( start_date )
		date_accum.accum_all( input_dates )
		dates = date_accum.get_dates()
		
		assert_that( dates, not_none() )
		assert_that( dates, has_length( 5 ) )	
	
_cd = namedtuple( '_cd', ( 'created', 'creator' ))
_cr = namedtuple( '_cr', 'username' )		
		
class TestBuckets( unittest.TestCase ):
	
	def setUp(self):
		for_credit = 'for_credit1'
		# Five different weeks with values over a five week window
		#Week1
		d1 = _cd( datetime( year=2014, month=3, day=28, hour=0, minute=30 ), _cr( for_credit ) )
		#Week2, seven total
		d2 = _cd( datetime( year=2014, month=4, day=1, hour=0, minute=30 ), _cr( for_credit ) )
		d3 = _cd( datetime( year=2014, month=4, day=2, hour=0, minute=30 ), _cr( for_credit ) )
		d4 = _cd( datetime( year=2014, month=4, day=3, hour=0, minute=30 ), _cr( for_credit ) )
		d5 = _cd( datetime( year=2014, month=4, day=4, hour=0, minute=30 ), _cr( for_credit ) )
		d6 = _cd( datetime( year=2014, month=4, day=5, hour=0, minute=30 ), _cr( for_credit ) )
		d7 = _cd( datetime( year=2014, month=4, day=5, hour=0, minute=30 ), _cr( for_credit ) )
		d8 = _cd( datetime( year=2014, month=4, day=5, hour=0, minute=30 ), _cr( for_credit ) )
		#Week3
		d9 = _cd( datetime( year=2014, month=4, day=9, hour=0, minute=30 ), _cr( for_credit ) )
		#Week4
		#Week5
		d10 = _cd( datetime( year=2014, month=4, day=27, hour=0, minute=30 ), _cr( for_credit ) )
		self.objects = [d1,d2,d3,d4,d5,d6,d7,d8,d9,d10]
			
	def test_empty(self):
		empty_objects = []
		empty_for_credit = []
		buckets = _common_buckets( empty_objects, _MockReport( [] ), datetime.now() )
		assert_that( buckets, not_none() )
		assert_that( buckets.count_by_day, empty() )
		assert_that( buckets.count_by_week_number, empty() )
		assert_that( buckets.top_creators, not_none() )
		assert_that( buckets.group_dates, empty() )
		
	def test_buckets(self):
		empty_for_credit = []
		start_date = datetime( year=2014, month=4, day=5, hour=0, minute=30 )
		buckets = _common_buckets( self.objects, _MockReport( [] ), start_date )
		assert_that( buckets, not_none() )
		#We have a bucket for each week
		assert_that( buckets.count_by_week_number, has_length( 4 ) )
		assert_that( buckets.top_creators, not_none() )
		#Our display field 'group_dates' covers all five weeks
		assert_that( buckets.group_dates, has_length( 5 ) )
		
		#Verify bucket totals
		assert_that( buckets.count_by_week_number[-1], equal_to( 1 ) )
		assert_that( buckets.count_by_week_number[0], equal_to( 7 ) )
		assert_that( buckets.count_by_week_number[1], equal_to( 1 ) )
		assert_that( buckets.count_by_week_number[3], equal_to( 1 ) )
		
		#Different start dates do not change counts
		start_date = datetime( year=2014, month=12, day=5, hour=0, minute=30 )
		buckets = _common_buckets( self.objects, _MockReport( [] ), start_date )
		
		#We have a bucket for each week
		assert_that( buckets.count_by_week_number, has_length( 4 ) )
		assert_that( buckets.top_creators, not_none() )
		#Our display field 'group_dates' covers all five weeks
		assert_that( buckets.group_dates, has_length( 5 ) )
		
		start_date = datetime( year=2011, month=3, day=5, hour=0, minute=30 )
		buckets = _common_buckets( self.objects, _MockReport( [] ), start_date )
		#We have a bucket for each week
		assert_that( buckets.count_by_week_number, has_length( 4 ) )
		assert_that( buckets.top_creators, not_none() )
		#Our display field 'group_dates' covers all five weeks
		assert_that( buckets.group_dates, has_length( 5 ) )
		
	def test_empty_options(self):
		empty_objects = []
		empty_for_credit = []
		options = {}
		buckets = _common_buckets( empty_objects, _MockReport( [] ), datetime.now() )	
		forum_stat = _build_buckets_options( options, buckets )
		
		assert_that( forum_stat, not_none() )
		assert_that( forum_stat.forum_objects_by_day, has_length( 0 ) )
		assert_that( forum_stat.forum_objects_by_week_number, has_length( 0 ) )
		assert_that( forum_stat.forum_objects_by_week_number_series, has_length( 0 ) )
		assert_that( forum_stat.forum_objects_by_week_number_max, not_none() )
		assert_that( forum_stat.forum_objects_by_week_number_value_min, not_none() )
		assert_that( forum_stat.forum_objects_by_week_number_value_max, not_none() )
		assert_that( forum_stat.forum_objects_by_week_number_categories, not_none() )
		
	def test_options(self):	
		empty_for_credit = []
		options = {}
		start_date = datetime( year=2014, month=4, day=5, hour=0, minute=30 )
		buckets = _common_buckets( self.objects, _MockReport( [] ), start_date )
		
		forum_stat = _build_buckets_options( options, buckets )
		
		assert_that( forum_stat, not_none() )
		assert_that( forum_stat.forum_objects_by_week_number, has_length( 4 ) )
		assert_that( 	forum_stat.forum_objects_by_week_number_series(), 
						has_length( greater_than( 4 ) ) )
		assert_that( forum_stat.forum_objects_by_week_number_max, not_none( ) )
		assert_that( forum_stat.forum_objects_by_week_number_value_min, not_none() )
		assert_that( forum_stat.forum_objects_by_week_number_value_max, not_none() )
		assert_that( 	forum_stat.forum_objects_by_week_number_categories, 
						has_length( greater_than_or_equal_to( 5 ) ) )

def _mock_student_info( self_placeholder, username ):
	return _StudentInfo( username + "_alias", username )	
	
class _MockReport(object):
	
	for_credit_student_usernames = []
	open_student_usernames = []
	get_student_info = _mock_student_info
	count_all_students = 0
	count_credit_students = 0
	count_non_credit_students = 0
	
	def __init__( self, for_credit_students=[], non_credit_students=[] ):
		self.for_credit_student_usernames = for_credit_students
		self.open_student_usernames = non_credit_students
		
class TestTopCreators( unittest.TestCase ):
	
	def setUp(self):
		self.top_creators = _TopCreators( _MockReport( [] ) )
	
	def test_empty(self):
		assert_that( self.top_creators._for_credit_data, empty() )
		assert_that( self.top_creators._non_credit_data, empty() )
		assert_that( self.top_creators._get_largest(), empty() )
		assert_that( self.top_creators._get_for_credit_largest(), empty() )
		assert_that( self.top_creators.series(), not_none() )
		assert_that( self.top_creators.unique_contributors_for_credit, equal_to( 0 ) )
		assert_that( self.top_creators.unique_contributors_non_credit, equal_to( 0 ) )
		assert_that( self.top_creators.for_credit_total, equal_to( 0 ) )
		assert_that( self.top_creators.non_credit_total, equal_to( 0 ) )
		assert_that( self.top_creators.keys(), empty() )
		assert_that( self.top_creators.for_credit_keys(), empty() )
		assert_that( self.top_creators.non_credit_keys(), empty() )
		
		student_info = self.top_creators._build_student_info( ('user1',100) )
		assert_that( student_info.username , equal_to( 'user1' ) )
		assert_that( student_info.display , equal_to( 'user1_alias' ) )
		assert_that( student_info.count , equal_to( 100 ) )
		assert_that( student_info.perc , equal_to( 0.0 ) )
		
		assert_that( self.top_creators.get( 'bleh' ), none() )
		assert_that( self.top_creators.average_count(), equal_to( 0 ) )
		assert_that( self.top_creators.average_count_str, not_none() )
		assert_that( self.top_creators.percent_contributed( 0, 0 ), equal_to( 100 ) ) 
		assert_that( self.top_creators.percent_contributed_str(), not_none() ) 
		assert_that( self.top_creators.for_credit_percent_contributed_str(), not_none() ) 
		assert_that( self.top_creators.non_credit_percent_contributed_str(), not_none() ) 
		
		
	def test_single(self):
		for_credit = 'for_credit1'
		self.top_creators = _TopCreators( _MockReport( [ for_credit ] ) )
		self.top_creators.incr_username( for_credit )
		
		assert_that( self.top_creators.total, equal_to( 1 ) )
		
		assert_that( self.top_creators._for_credit_data, has_length( 1 ) )
		assert_that( self.top_creators._for_credit_data.keys(), only_contains( for_credit ) )
		assert_that( self.top_creators._non_credit_data, empty() )
		assert_that( self.top_creators._get_largest(), has_length( 1 ) )
		assert_that( self.top_creators._get_for_credit_largest(), has_length( 1 ) )
		assert_that( self.top_creators.unique_contributors_for_credit, equal_to( 1 ) )
		assert_that( self.top_creators.unique_contributors_non_credit, equal_to( 0 ) )
		assert_that( self.top_creators.for_credit_total, equal_to( 1 ) )
		assert_that( self.top_creators.non_credit_total, equal_to( 0 ) )
		assert_that( len( self.top_creators.keys() ), equal_to( 1 ) )
		assert_that( self.top_creators.keys(), only_contains( for_credit ) )
		assert_that( len( self.top_creators.for_credit_keys() ), equal_to( 1 ) )
		assert_that( self.top_creators.for_credit_keys(), only_contains( for_credit ) )
		assert_that( self.top_creators.non_credit_keys(), empty() )
		
		student_info = self.top_creators._build_student_info( ('user1', 0 ) )
		assert_that( student_info.username, equal_to( 'user1' ) )
		assert_that( student_info.display, equal_to( 'user1_alias' ) )
		assert_that( student_info.count, equal_to( 0 ) )
		assert_that( student_info.perc, equal_to( 0.0 ) )
		
		student_info = self.top_creators._build_student_info( ('for_credit1', 1 ) )
		assert_that( student_info.username, equal_to( 'for_credit1' ) )
		assert_that( student_info.display, equal_to( 'for_credit1_alias' ) )
		assert_that( student_info.count, equal_to( 1 ) )
		assert_that( student_info.perc, equal_to( 100 ) )
		
		assert_that( self.top_creators.get( 'bleh' ), none() )
		assert_that( self.top_creators.get( 'for_credit1' ), equal_to( 1 ) )
		assert_that( self.top_creators.average_count(), equal_to( 1 ) )
		assert_that( self.top_creators.average_count_str, not_none() )
		assert_that( self.top_creators.percent_contributed( 1, 1 ), equal_to( 100 ) ) 
		assert_that( self.top_creators.percent_contributed_str(), not_none() ) 
		assert_that( self.top_creators.for_credit_percent_contributed_str(), not_none() ) 
		assert_that( self.top_creators.non_credit_percent_contributed_str(), not_none() ) 	
		
	def test_multiple(self):
		for_credit = 'for_credit1'
		for_credit2 = 'for_credit2'
		non_credit1 = 'non_credit1'
		non_credit2 = 'non_credit2'
		
		self.top_creators = _TopCreators( _MockReport( [ for_credit, for_credit2 ], [non_credit1,non_credit2] ) )
		
		for i in range(5):
			self.top_creators.incr_username( for_credit )
			self.top_creators.incr_username( non_credit1 )
		
		for i in range(10):
			self.top_creators.incr_username( non_credit2 )

		assert_that( self.top_creators.total, equal_to( 20 ) )
		assert_that( self.top_creators._for_credit_data, has_length( 1 ) )
		assert_that( 	self.top_creators._for_credit_data.keys(), 
						only_contains( for_credit ) )
		assert_that( self.top_creators._non_credit_data, has_length( 2 ) )
		assert_that( 	self.top_creators._non_credit_data.keys(), 
						only_contains( non_credit1, non_credit2 ) )
		assert_that( self.top_creators._get_largest(), has_length( 3 ) )
		assert_that( 	self.top_creators._get_largest()[0].username, 
						equal_to( 'non_credit2' ) ) 
		assert_that( self.top_creators._get_for_credit_largest(), has_length( 1 ) )
		assert_that( self.top_creators.unique_contributors_for_credit, equal_to( 1 ) )
		assert_that( self.top_creators.unique_contributors_non_credit, equal_to( 2 ) )
		assert_that( self.top_creators.for_credit_total, equal_to( 5 ) )
		assert_that( self.top_creators.non_credit_total, equal_to( 15 ) )
		assert_that( len( self.top_creators.keys() ), equal_to( 3 ) )
		assert_that( 	self.top_creators.keys(), 
						only_contains( for_credit, non_credit1, non_credit2 ) )
		assert_that( len( self.top_creators.for_credit_keys() ), equal_to( 1 ) )
		assert_that( self.top_creators.for_credit_keys(), only_contains( for_credit ) )
		assert_that( self.top_creators.non_credit_keys(), only_contains( non_credit1, non_credit2 ) )
		
		student_info = self.top_creators._build_student_info( ('user1', 0 ) )
		assert_that( student_info.username, equal_to( 'user1' ) )
		assert_that( student_info.display, equal_to( 'user1_alias' ) )
		assert_that( student_info.count, equal_to( 0 ) )
		assert_that( student_info.perc, equal_to( 0.0 ) )
		
		student_info = self.top_creators._build_student_info( ('for_credit1', 5 ) )
		assert_that( student_info.username, equal_to( 'for_credit1' ) )
		assert_that( student_info.display, equal_to( 'for_credit1_alias' ) )
		assert_that( student_info.count, equal_to( 5 ) )
		assert_that( student_info.perc, equal_to( 25 ) )
		
		assert_that( self.top_creators.get( 'bleh' ), none() )
		assert_that( self.top_creators.get( 'for_credit1' ), equal_to( 5 ) )
		assert_that( self.top_creators.average_count(), close_to( 6.6, .1 ) )
		assert_that( self.top_creators.average_count_str, not_none() )
		assert_that( self.top_creators.percent_contributed( 1, 1 ), equal_to( 100 ) ) 
		assert_that( self.top_creators.percent_contributed_str(), not_none() ) 
		assert_that( self.top_creators.for_credit_percent_contributed_str(), not_none() ) 
		assert_that( self.top_creators.non_credit_percent_contributed_str(), not_none() ) 	

_report = namedtuple( '_report', ( 	'for_credit_student_usernames', 
									'open_student_usernames', 
									'count_all_students',
									'count_credit_students',
									'count_non_credit_students' ) )
_grade = namedtuple( '_grade', 'value' )
		
class _Column(object):
	
	def __init__( self, displayName, DueDate, objects ):	
		self.displayName = displayName
		self.DueDate = DueDate
		self.objects = objects
	
	def len(self):
		return len(self.objects)
	
	def __len__(self):
		return self.len()
		
	def __iter__(self):
		return (x for x in self.objects)
	
	def items(self):
		return self.objects.items()
	
class TestBuildAssignmentStats( unittest.TestCase ):
	
	def test_empty(self):
		report = _report( set(), set(), 0, 0 , 0 )
		col = _Column( 'bane', 'date', {} )
		stat = _assignment_stat_for_column( report, col )		
		assert_that( stat, not_none() )
		assert_that( stat, is_( _AssignmentStat ) )
		
	def test_building(self):
		report = _report( {'fc1','fc2'}, {'nc1','nc2'}, 4, 2, 2 )
		col_items = { 	'fc1':_grade(40), 
						'fc2':_grade(80), 
						'nc2':_grade(30), 
						'dropped':_grade(0)  }
		col = _Column( 'name1', 'date1', col_items )
		stat = _assignment_stat_for_column( report, col )		

		assert_that( stat, not_none() )
		assert_that( stat, is_( _AssignmentStat ) )
		assert_that( stat.count, is_( 4 ) )
		assert_that( stat.total, is_( 3 ) )
		assert_that( stat.for_credit_total, is_( 2 ) )
		assert_that( stat.non_credit_total, is_( 1 ) )
		assert_that( stat.avg_grade, is_( '50.0' ) )
		assert_that( stat.for_credit_avg_grade, is_( '60.0' ) )
		assert_that( stat.non_credit_avg_grade, is_( '30.0' ) )
		assert_that( stat.attempted_perc, not_none() )
		assert_that( stat.for_credit_attempted_perc, not_none() )
		assert_that( stat.non_credit_attempted_perc, not_none() )
		
	def test_building_filter(self):
		report = _report( {'fc1','fc2'}, {'nc1','nc2'}, 4, 2, 2 )
		col_items = { 	'fc1':_grade(40), 
						'fc2':_grade(80), 
						'nc2':_grade(30), 
						'dropped':_grade(0)  }
		filter = {'fc2'}
		col = _Column( 'name1', 'date1', col_items )
		stat = _assignment_stat_for_column( report, col, filter )		

		assert_that( stat, not_none() )
		assert_that( stat, is_( _AssignmentStat ) )
		assert_that( stat.count, is_( 4 ) )
		assert_that( stat.total, is_( 1 ) )
		assert_that( stat.for_credit_total, is_( 1 ) )
		assert_that( stat.non_credit_total, is_( 0 ) )
		assert_that( stat.avg_grade, is_( '80.0' ) )
		assert_that( stat.for_credit_avg_grade, is_( '80.0' ) )
		assert_that( stat.non_credit_avg_grade, is_( 'N/A' ) )
		assert_that( stat.attempted_perc, not_none() )
		assert_that( stat.for_credit_attempted_perc, not_none() )
		assert_that( stat.non_credit_attempted_perc, not_none() )
		
		
		
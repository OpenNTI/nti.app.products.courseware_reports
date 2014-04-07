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

from collections import namedtuple

from datetime import datetime

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
		buckets = _common_buckets( empty_objects, empty_for_credit, _mock_student_info, datetime.now() )
		assert_that( buckets, not_none() )
		assert_that( buckets.count_by_day, empty() )
		assert_that( buckets.count_by_week_number, empty() )
		assert_that( buckets.top_creators, not_none() )
		assert_that( buckets.group_dates, empty() )
		
	def test_buckets(self):
		empty_for_credit = []
		start_date = datetime( year=2014, month=4, day=5, hour=0, minute=30 )
		buckets = _common_buckets( self.objects, empty_for_credit, _mock_student_info, start_date )
		assert_that( buckets, not_none() )
		assert_that( buckets.count_by_day, has_length( 8 ) )
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
		buckets = _common_buckets( self.objects, empty_for_credit, _mock_student_info, start_date )
		assert_that( buckets.count_by_day, has_length( 8 ) )
		#We have a bucket for each week
		assert_that( buckets.count_by_week_number, has_length( 4 ) )
		assert_that( buckets.top_creators, not_none() )
		#Our display field 'group_dates' covers all five weeks
		assert_that( buckets.group_dates, has_length( 5 ) )
		
		start_date = datetime( year=2011, month=3, day=5, hour=0, minute=30 )
		buckets = _common_buckets( self.objects, empty_for_credit, _mock_student_info, start_date )
		assert_that( buckets.count_by_day, has_length( 8 ) )
		#We have a bucket for each week
		assert_that( buckets.count_by_week_number, has_length( 4 ) )
		assert_that( buckets.top_creators, not_none() )
		#Our display field 'group_dates' covers all five weeks
		assert_that( buckets.group_dates, has_length( 5 ) )
		
	def test_empty_options(self):
		empty_objects = []
		empty_for_credit = []
		options = {}
		buckets = _common_buckets( empty_objects, empty_for_credit, _mock_student_info, datetime.now() )	
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
		buckets = _common_buckets( self.objects, empty_for_credit, _mock_student_info, start_date )
		
		forum_stat = _build_buckets_options( options, buckets )
		
		assert_that( forum_stat, not_none() )
		assert_that( forum_stat.forum_objects_by_day, has_length( 8 ) )
		assert_that( forum_stat.forum_objects_by_week_number, has_length( 4 ) )
		assert_that( 	forum_stat.forum_objects_by_week_number_series(), 
						has_length( greater_than( 4 ) ) )
		assert_that( forum_stat.forum_objects_by_week_number_max, not_none( ) )
		assert_that( forum_stat.forum_objects_by_week_number_value_min, not_none() )
		assert_that( forum_stat.forum_objects_by_week_number_value_max, not_none() )
		assert_that( 	forum_stat.forum_objects_by_week_number_categories, 
						has_length( greater_than_or_equal_to( 5 ) ) )

def _mock_student_info( username ):
	return _StudentInfo( username + "_alias", username )	
		
class TestTopCreators( unittest.TestCase ):
	
	def setUp(self):
		self.top_creators = _TopCreators( [], _mock_student_info )
	
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
		self.top_creators = _TopCreators( [ for_credit ], _mock_student_info )
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
		
		self.top_creators = _TopCreators( [ for_credit, for_credit2 ], _mock_student_info )
		
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
		
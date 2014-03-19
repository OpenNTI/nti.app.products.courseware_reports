#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""


.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

#disable: accessing protected members, too many methods
#pylint: disable=W0212,R0904

from hamcrest import assert_that
from hamcrest import has_property
from hamcrest import contains_string

from nti.app.testing.application_webtest import ApplicationLayerTest
from nti.app.testing.decorators import WithSharedApplicationMockDS

from nti.app.products.courseware.tests import InstructedCourseApplicationTestLayer

from .. import VIEW_STUDENT_PARTICIPATION
from .. import VIEW_FORUM_PARTICIPATION
from .. import VIEW_TOPIC_PARTICIPATION
from .. import VIEW_COURSE_SUMMARY

class TestStudentParticipationReport(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.

		# This only works in the OU environment because that's where the purchasables are
		extra_env = self.testapp.extra_environ or {}
		extra_env.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		self.testapp.extra_environ = extra_env

		enrollment_res = self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
												 'CLC 3403',
												 status=201 )

		view_href = self.require_link_href_with_rel( enrollment_res.json_body, 'report-%s' % VIEW_STUDENT_PARTICIPATION )
		assert_that( view_href, contains_string( 'users/sjohnson%40nextthought.com' ) )
		
		res = self.testapp.get( view_href )
		assert_that( res, has_property('content_type', 'application/pdf') )


class TestForumParticipationReport(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.

		# This only works in the OU environment because that's where the purchasables are
		extra_env = self.testapp.extra_environ or {}
		extra_env.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		self.testapp.extra_environ = extra_env

		enrollment_res = self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
								'CLC 3403',
								status=201 )

		board_href = enrollment_res.json_body['CourseInstance']['Discussions']['href']
		forum_href = board_href + '/Forum'
		report_href = forum_href + '/' + VIEW_FORUM_PARTICIPATION

		res = self.testapp.get(report_href)
		assert_that( res, has_property('content_type', 'application/pdf'))


class TestTopicParticipationReport(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.

		# This only works in the OU environment because that's where the purchasables are
		extra_env = self.testapp.extra_environ or {}
		extra_env.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		self.testapp.extra_environ = extra_env

		enrollment_res = self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
								'CLC 3403',
								status=201 )

		board_href = enrollment_res.json_body['CourseInstance']['Discussions']['href']
		forum_href = board_href + '/Forum'

		# Create a topic
		res = self.testapp.post_json( forum_href,{'Class': 'Post', 'body': ['My body'], 'title': 'my title'} )
		topic_href = res.json_body['href']

		report_href = topic_href + '/' + VIEW_TOPIC_PARTICIPATION

		res = self.testapp.get(report_href)
		assert_that( res, has_property('content_type', 'application/pdf'))

class TestCourseSummaryReport(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.

		# This only works in the OU environment because that's where the purchasables are
		extra_env = self.testapp.extra_environ or {}
		extra_env.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		self.testapp.extra_environ = extra_env

		enrollment_res = self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
								'CLC 3403',
								status=201 )

		course_href = enrollment_res.json_body['CourseInstance']['href']

		res = self.testapp.get(course_href + '/' + VIEW_COURSE_SUMMARY )
		assert_that( res, has_property('content_type', 'application/pdf'))

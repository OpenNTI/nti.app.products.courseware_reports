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
from .. import VIEW_ASSIGNMENT_SUMMARY

from nti.app.assessment.tests import RegisterAssignmentsForEveryoneLayer
from nti.app.assessment.tests import RegisterAssignmentLayerMixin


class TestStudentParticipationReport(ApplicationLayerTest):

	layer = RegisterAssignmentsForEveryoneLayer

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.

		# This only works in the OU environment because that's where the purchasables are
		extra_env = self.testapp.extra_environ or {}
		extra_env.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		self.testapp.extra_environ = extra_env

		instructor_environ = self._make_extra_environ(username='harp4162')
		instructor_environ.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		enrollment_res = self.testapp.post_json( '/dataserver2/users/harp4162/Courses/EnrolledCourses',
												 'CLC 3403',
												 status=201,
												 extra_environ=instructor_environ)

		view_href = self.require_link_href_with_rel( enrollment_res.json_body, 'report-%s' % VIEW_STUDENT_PARTICIPATION )


		res = self.testapp.get(view_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf'))

class TestForumParticipationReport(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.

		# This only works in the OU environment because that's where the purchasables are
		#/dataserver2/users/CHEM4970.ou.nextthought.com/DiscussionBoard/
		extra_env = self.testapp.extra_environ or {}
		extra_env.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		self.testapp.extra_environ = extra_env

		enrollment_res = self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
								'CLC 3403',
								status=201 )

		board_href = enrollment_res.json_body['CourseInstance']['Discussions']['href']
		forum_href = board_href + '/Forum'
		instructor_environ = self._make_extra_environ(username='harp4162')

		forum_res = self.testapp.get( forum_href, extra_environ=instructor_environ )

		report_href = self.require_link_href_with_rel( forum_res.json_body, 'report-' + VIEW_FORUM_PARTICIPATION )
		assert_that( report_href, contains_string( 'CLC3403.ou.nextthought.com' ) )

		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf') )

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
		instructor_environ = self._make_extra_environ(username='harp4162')
		# Create a topic
		res = self.testapp.post_json( forum_href,{'Class': 'Post', 'body': ['My body'], 'title': 'my title'},
									  extra_environ=instructor_environ)
		report_href = self.require_link_href_with_rel( res.json_body, 'report-' + VIEW_TOPIC_PARTICIPATION )
		assert_that( report_href, contains_string( 'CLC3403.ou.nextthought.com' ) )

		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf') )

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

		instructor_environ = self._make_extra_environ(username='harp4162')
		instructor_environ.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		enrollment_res = self.testapp.post_json( '/dataserver2/users/harp4162/Courses/EnrolledCourses',
												 'CLC 3403',
												 status=201,
												 extra_environ=instructor_environ)

		course = enrollment_res.json_body['CourseInstance']
		report_href = self.require_link_href_with_rel( course, 'report-' + VIEW_COURSE_SUMMARY )
		assert_that( report_href, contains_string( 'CLC3403.ou.nextthought.com' ) )

		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf') )


from nti.externalization.externalization import to_external_object
from nti.assessment.submission import AssignmentSubmission
from nti.assessment.submission import QuestionSetSubmission


class TestAssignmentSummaryReport(RegisterAssignmentLayerMixin,
								  ApplicationLayerTest):

	layer = RegisterAssignmentsForEveryoneLayer

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.

		# This only works in the OU environment because that's where the purchasables are
		extra_env = self.testapp.extra_environ or {}
		extra_env.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		self.testapp.extra_environ = extra_env
		instructor_environ = self._make_extra_environ(username='harp4162')
		res = self.testapp.get( '/dataserver2/users/CLC3403.ou.nextthought.com/LegacyCourses/CLC3403/GradeBook/default',
								extra_environ=instructor_environ)

		assignment = res.json_body['Items']['Assignment 1']
		report_href = self.require_link_href_with_rel( assignment, 'report-' + VIEW_ASSIGNMENT_SUMMARY )
		assert_that( report_href, contains_string( 'default/Assignment%201' ) )

		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf'))


	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_report(self):
		# This only works in the OU environment because that's where the purchasables are
		extra_env = self.testapp.extra_environ or {}
		extra_env.update( {b'HTTP_ORIGIN': b'http://janux.ou.edu'} )
		self.testapp.extra_environ = extra_env
		instructor_environ = self._make_extra_environ(username='harp4162')
		res = self.testapp.get( '/dataserver2/users/CLC3403.ou.nextthought.com/LegacyCourses/CLC3403/GradeBook/default',
								extra_environ=instructor_environ)

		assignment = res.json_body['Items']['Assignment 1']
		report_href = self.require_link_href_with_rel( assignment, 'report-' + VIEW_ASSIGNMENT_SUMMARY )
		assert_that( report_href, contains_string( 'default/Assignment%201' ) )

		# Sends an assignment through the application by posting to the assignment
		qs_submission = QuestionSetSubmission(questionSetId=self.question_set_id)
		submission = AssignmentSubmission(assignmentId=self.assignment_id, parts=(qs_submission,))

		ext_obj = to_external_object( submission )

		self.testapp.post_json( '/dataserver2/Objects/' + self.assignment_id,
								ext_obj)
		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf'))

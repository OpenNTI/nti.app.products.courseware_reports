#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import assert_that
from hamcrest import has_property
from hamcrest import contains_string

from .. import VIEW_COURSE_SUMMARY
from .. import VIEW_ASSIGNMENT_SUMMARY
from .. import VIEW_FORUM_PARTICIPATION
from .. import VIEW_TOPIC_PARTICIPATION
from .. import VIEW_STUDENT_PARTICIPATION

from nti.app.products.courseware.tests import InstructedCourseApplicationTestLayer

from nti.app.assessment.tests import RegisterAssignmentLayerMixin
from nti.app.assessment.tests import RegisterAssignmentsForEveryoneLayer

from nti.app.testing.decorators import WithSharedApplicationMockDS
from nti.app.testing.application_webtest import ApplicationLayerTest


class TestStudentParticipationReport(ApplicationLayerTest):

	layer = RegisterAssignmentsForEveryoneLayer

	# This only works in the OU environment because that's where the purchasables are
	default_origin = b'http://janux.ou.edu'

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.
		self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
								'CLC 3403',
								status=201 )

		instructor_environ = self._make_extra_environ(username='harp4162')
		admin_courses = self.testapp.get( '/dataserver2/users/harp4162/Courses/AdministeredCourses/',
										extra_environ=instructor_environ)

		# Get our student from the roster
		course_instance = admin_courses.json_body.get( 'Items' )[0].get( 'CourseInstance' )
		roster_link = self.require_link_href_with_rel( course_instance, 'CourseEnrollmentRoster')
		sj_enrollment = self.testapp.get( roster_link,
										extra_environ=instructor_environ)
		sj_enrollment = sj_enrollment.json_body.get( 'Items' )[0]

		view_href = self.require_link_href_with_rel( sj_enrollment,
													'report-%s' % VIEW_STUDENT_PARTICIPATION )


		res = self.testapp.get(view_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf'))

class TestForumParticipationReport(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	# This only works in the OU environment because that's where the purchasables are
	default_origin = b'http://janux.ou.edu'


	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.

		enrollment_res = self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
								'CLC 3403',
								status=201 )

		board_href = enrollment_res.json_body['CourseInstance']['Discussions']['href']
		forum_href = board_href + '/Forum'
		instructor_environ = self._make_extra_environ(username='harp4162')

		forum_res = self.testapp.get( forum_href, extra_environ=instructor_environ )

		report_href = self.require_link_href_with_rel( forum_res.json_body, 'report-' + VIEW_FORUM_PARTICIPATION )
		assert_that( report_href, contains_string( 'CLC3403' ) )

		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf') )

class TestTopicParticipationReport(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	# This only works in the OU environment because that's where the purchasables are
	default_origin = b'http://janux.ou.edu'


	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.
		enrollment_res = self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
								'CLC 3403',
								status=201 )

		board_href = enrollment_res.json_body['CourseInstance']['Discussions']['href']
		forum_href = board_href + '/Forum'
		instructor_environ = self._make_extra_environ(username='harp4162')

		# Create a topic
		res = self.testapp.post_json( forum_href,
									  {'Class': 'Post', 'body': ['My body'], 'title': 'my title'},
									  extra_environ=instructor_environ)
		report_href = self.require_link_href_with_rel( res.json_body, 'report-' + VIEW_TOPIC_PARTICIPATION )
		assert_that( report_href, contains_string( 'CLC3403' ) )

		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf') )

class TestCourseSummaryReport(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	# This only works in the OU environment because that's where the purchasables are
	default_origin = b'http://janux.ou.edu'

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.
		instructor_environ = self._make_extra_environ(username='harp4162')
		admin_courses = self.testapp.get( '/dataserver2/users/harp4162/Courses/AdministeredCourses/',
										extra_environ=instructor_environ)

		course = admin_courses.json_body.get( 'Items' )[0].get( 'CourseInstance' )
		report_href = self.require_link_href_with_rel( course, 'report-' + VIEW_COURSE_SUMMARY )
		assert_that( report_href, contains_string( 'CLC3403' ) )

		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf') )

from nti.assessment.submission import AssignmentSubmission
from nti.assessment.submission import QuestionSetSubmission
from nti.externalization.externalization import to_external_object

class TestAssignmentSummaryReport(RegisterAssignmentLayerMixin,
								  ApplicationLayerTest):

	layer = RegisterAssignmentsForEveryoneLayer

	# This only works in the OU environment because that's where the purchasables are
	default_origin = b'http://janux.ou.edu'

	assignments_path = '/dataserver2/%2B%2Betc%2B%2Bhostsites/platform.ou.edu/%2B%2Betc%2B%2Bsite/Courses/Fall2013/CLC3403_LawAndJustice/AssignmentsByOutlineNode'

	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_empty_report(self):
		# Trivial test to make sure we can fetch the report even with
		# no data.
		instructor_environ = self._make_extra_environ(username='harp4162')
		res = self.testapp.get( self.assignments_path,
								extra_environ=instructor_environ)

		assignment = res.json_body.get( 'Items' )['tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.sec:QUIZ_01.01'][0]
		report_href = self.require_link_href_with_rel( assignment, 'report-' + VIEW_ASSIGNMENT_SUMMARY )
		assert_that( report_href, contains_string( 'default/Assignment%201' ) )

		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf'))


	@WithSharedApplicationMockDS(users=True,testapp=True,default_authenticate=True)
	def test_application_view_report(self):
		instructor_environ = self._make_extra_environ(username='harp4162')
		res = self.testapp.get( self.assignments_path,
								extra_environ=instructor_environ)

		assignment = res.json_body.get( 'Items' )['tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.sec:QUIZ_01.01'][0]
		report_href = self.require_link_href_with_rel( assignment, 'report-' + VIEW_ASSIGNMENT_SUMMARY )
		assert_that( report_href, contains_string( 'default/Assignment%201' ) )

		# Sends an assignment through the application by posting to the assignment
		qs_submission = QuestionSetSubmission(questionSetId=self.question_set_id)
		submission = AssignmentSubmission(assignmentId=self.assignment_id, parts=(qs_submission,))

		ext_obj = to_external_object( submission )

		# enroll
		self.testapp.post_json( '/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
								'CLC 3403',
								status=201 )


		self.testapp.post_json( '/dataserver2/Objects/' + self.assignment_id,
								ext_obj)
		res = self.testapp.get(report_href, extra_environ=instructor_environ)
		assert_that( res, has_property('content_type', 'application/pdf'))

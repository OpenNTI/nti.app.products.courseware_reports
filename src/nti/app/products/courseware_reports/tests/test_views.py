#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904


from hamcrest import is_
from hamcrest import is_not
from hamcrest import has_key
from hamcrest import has_item
from hamcrest import assert_that
from hamcrest import has_entries
from hamcrest import has_entry
from hamcrest import has_property
from hamcrest import contains_string
from hamcrest import has_items
from hamcrest import none
from hamcrest import described_as
from hamcrest import has_length
from hamcrest import equal_to


import csv
import fudge
from six import StringIO

from nti.app.analytics.usage_stats import _VideoInfo
from nti.app.analytics.usage_stats import _AverageWatchTimes

from nti.app.products.courseware_reports import VIEW_COURSE_SUMMARY
from nti.app.products.courseware_reports import VIEW_ASSIGNMENT_SUMMARY
from nti.app.products.courseware_reports import VIEW_FORUM_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_TOPIC_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_STUDENT_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_INQUIRY_REPORT
from nti.app.products.courseware_reports import VIEW_USER_ENROLLMENT
from nti.app.products.courseware_reports import VIEW_COURSE_ROSTER

from nti.dataserver.users.users import User

from nti.app.products.courseware_reports.views.participation_views import StudentParticipationReportPdf

from nti.app.products.courseware_reports.views.user_views import UserEnrollmentReportPdf
from nti.app.products.courseware_reports.views.course_roster_views import CourseRosterReportPdf

from nti.app.products.courseware_reports.views.admin_views import StudentParticipationCSVView

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.app.assessment.tests import RegisterAssignmentLayerMixin
from nti.app.assessment.tests import RegisterAssignmentsForEveryoneLayer

from nti.app.products.courseware.tests import InstructedCourseApplicationTestLayer

from nti.app.testing.application_webtest import ApplicationLayerTest

from nti.app.testing.decorators import WithSharedApplicationMockDS

from nti.app.testing.request_response import DummyRequest

from nti.assessment.survey import QPollSubmission

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.dataserver.tests import mock_dataserver

def _require_link_with_title(item, title):
    assert_that(item,
                    has_entry("Links",
                              (has_item(has_entry("title", title)))))

def _require_report_with_title(item, title):
    assert_that(item,
                has_entry("Reports",
                          (has_item(has_entry("title", title)))))

class TestStudentParticipationReport(ApplicationLayerTest):

    layer = RegisterAssignmentsForEveryoneLayer
    default_origin = b'http://janux.ou.edu'
    course_ntiid = 'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_application_view_empty_report(self):
        # Trivial test to make sure we can fetch the report even with
        # no data.
        self.testapp.post_json('/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
                               'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2013_CLC3403_LawAndJustice',
                               status=201)

        instructor_environ = self._make_extra_environ(username='harp4162')
        admin_courses = self.testapp.get('/dataserver2/users/harp4162/Courses/AdministeredCourses/',
                                         extra_environ=instructor_environ)

        # Get our student from the roster
        course_instance = admin_courses.json_body.get(
            'Items')[0].get('CourseInstance')
        roster_link = self.require_link_href_with_rel(
            course_instance, 'CourseEnrollmentRoster')
        sj_enrollment = self.testapp.get(roster_link,
                                         extra_environ=instructor_environ)

        sj_enrollment = sj_enrollment.json_body.get('Items')[0]

        view_href = self.require_link_href_with_rel(sj_enrollment,
                                                    'report-%s' % VIEW_STUDENT_PARTICIPATION)

        _require_link_with_title(sj_enrollment, "Student Participation Report")

        res = self.testapp.get(view_href, extra_environ=instructor_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

        # check admin role fetch report
        admin_environ = self._make_extra_environ(username='sjohnson@nextthought.com')
        res = self.testapp.get(view_href, extra_environ=admin_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

        # check site admin role fetch report
        self.testapp.post_json('/dataserver2/SiteAdmins/harp4162',
                               status=200)
        site_admin_environ = self._make_extra_environ(username='harp4162')
        res = self.testapp.get(view_href, extra_environ=site_admin_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))


    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    @fudge.patch('nti.app.products.courseware_reports.views.view_mixins.AbstractCourseReportView._check_access',
                 'nti.app.analytics.usage_stats.UserCourseVideoUsageStats.get_stats')
    def test_report_completion_data(self, fake_check_access, fake_video_stats):

        fake_check_access.is_callable().returns(True)
        fake_video_stats.is_callable().returns([])

        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            obj = find_object_with_ntiid(self.course_ntiid)
            course = ICourseInstance(obj)
            request = DummyRequest(params={})

            participation_report = StudentParticipationReportPdf(
                course, request)

            student_user = User.get_user('sjohnson@nextthought.com')
            participation_report.student_user = student_user
            course.Username = student_user.username

            options = participation_report()

            # If we have not yet watched any videos, we should
            # have no entries with session count, view count,
            # total watch time, average session time, or
            # video completion.

            assert_that(options['video_completion'], is_not(
                has_item((has_key('session_count')))))
            assert_that(options['video_completion'], is_not(
                has_item((has_key('view_count')))))
            assert_that(options['video_completion'], is_not(
                has_item((has_key('total_watch_time')))))
            assert_that(options['video_completion'], is_not(
                has_item((has_key('average_session_watch_time')))))
            assert_that(options['video_completion'], is_not(
                has_item((has_key('video_completion')))))

            # Add stats for a video and check that they show up
            # correctly in the report
            video_ntiid = 'tag:nextthought.com,2011-10:OU-NTIVideo-CLC3403_LawAndJustice.ntivideo.video_02.01'

            fake_video_stats.is_callable().returns((_VideoInfo('fake title',
                                                               video_ntiid,
                                                               2,
                                                               3,
                                                               _AverageWatchTimes(
                                                                   '1:30', '2:30'),
                                                               '3:30',
                                                               '100',
                                                               1,
                                                               None),))
            options = participation_report()

            assert_that(
                options['video_completion'], has_item(has_entries('session_count', 2,
                                                                  'view_count', 3,
                                                                  'total_watch_time', '1:30',
                                                                  'average_session_watch_time', '2:30',
                                                                  'video_completion', True,
                                                                  'title', 'fake title')))


class TestInquiryReport(ApplicationLayerTest):

    layer = InstructedCourseApplicationTestLayer

    default_origin = b'http://janux.ou.edu'

    COURSE_NTIID = 'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2013_CLC3403_LawAndJustice'

    default_username = 'outest75'

    poll_ntiid = "tag:nextthought.com,2011-10:OU-NAQ-CLC3403_LawAndJustice.naq.pollid.aristotle.1"

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_link(self):
        instructor_environ = self._make_extra_environ(username='harp4162')
        res = self.testapp.get('/dataserver2/Objects/' + self.poll_ntiid,
                               extra_environ=instructor_environ)

        # No submissions, no report link
        self.forbid_link_with_rel(
            res.json_body,
            'report-' +
            VIEW_INQUIRY_REPORT)

        submission = QPollSubmission(pollId=self.poll_ntiid, parts=[0])

        ext_obj = to_external_object(submission)
        del ext_obj['Class']

        # Submit to a poll
        res = self.testapp.post_json('/dataserver2/users/' + self.default_username + '/Courses/EnrolledCourses',
                                     self.COURSE_NTIID,
                                     status=201)

        course_inquiries_link = self.require_link_href_with_rel(
            res.json_body['CourseInstance'], 'CourseInquiries')

        submission_href = '%s/%s' % (course_inquiries_link, self.poll_ntiid)

        res = self.testapp.post_json(submission_href, ext_obj)

        res = self.testapp.get('/dataserver2/Objects/' + self.poll_ntiid,
                               extra_environ=instructor_environ)

        # Now we should see the link
        self.require_link_href_with_rel(
            res.json_body, 'report-' + VIEW_INQUIRY_REPORT)

        _require_link_with_title(res.json_body, "Inquiry Report")

class TestForumParticipationReport(ApplicationLayerTest):

    layer = InstructedCourseApplicationTestLayer

    default_origin = b'http://janux.ou.edu'

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_link(self):
        enrollment_res = self.testapp.post_json('/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
                                                'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2013_CLC3403_LawAndJustice',
                                                status=201)

        board_href = enrollment_res.json_body[
            'CourseInstance']['Discussions']['href']
        forum_href = board_href + '/Forum'
        instructor_environ = self._make_extra_environ(username='harp4162')

        forum_res = self.testapp.get(
            forum_href, extra_environ=instructor_environ)

        self.forbid_link_with_rel(
            forum_res.json_body, 'report-' + VIEW_FORUM_PARTICIPATION)


class TestTopicParticipationReport(ApplicationLayerTest):

    layer = InstructedCourseApplicationTestLayer

    default_origin = b'http://janux.ou.edu'

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_link(self):
        enrollment_res = self.testapp.post_json('/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
                                                'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2013_CLC3403_LawAndJustice',
                                                status=201)

        board_href = enrollment_res.json_body[
            'CourseInstance']['Discussions']['href']
        forum_href = board_href + '/Forum'
        instructor_environ = self._make_extra_environ(username='harp4162')

        # Create a topic
        res = self.testapp.post_json(forum_href,
                                     {'Class': 'Post', 'body': [
                                         'My body'], 'title': 'my title'},
                                     extra_environ=instructor_environ)
        self.forbid_link_with_rel(
            res.json_body, 'report-' + VIEW_TOPIC_PARTICIPATION)


class TestCourseSummaryReport(ApplicationLayerTest):

    layer = InstructedCourseApplicationTestLayer

    default_origin = b'http://janux.ou.edu'

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_application_view_empty_report(self):
        # Trivial test to make sure we can fetch the report even with
        # no data.
        instructor_environ = self._make_extra_environ(username='harp4162')
        admin_courses = self.testapp.get('/dataserver2/users/harp4162/Courses/AdministeredCourses/',
                                         extra_environ=instructor_environ)

        course = admin_courses.json_body.get('Items')[0].get('CourseInstance')

        report_href = self.require_link_href_with_rel(
            course, 'report-' + VIEW_COURSE_SUMMARY)

        _require_link_with_title(course, "Course Summary Report")

        assert_that(report_href, contains_string('CLC3403'))

        res = self.testapp.get(report_href, extra_environ=instructor_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

        # check admin role fetch report
        admin_environ = self._make_extra_environ(username='sjohnson@nextthought.com')
        res = self.testapp.get(report_href, extra_environ=admin_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

        # check site admin role fetch report
        self.testapp.post_json('/dataserver2/SiteAdmins/harp4162',
                               status=200)
        site_admin_environ = self._make_extra_environ(username='harp4162')
        res = self.testapp.get(report_href, extra_environ=site_admin_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

from nti.assessment.submission import AssignmentSubmission
from nti.assessment.submission import QuestionSetSubmission
from nti.externalization.externalization import to_external_object


class TestAssignmentSummaryReport(RegisterAssignmentLayerMixin,
                                  ApplicationLayerTest):

    layer = RegisterAssignmentsForEveryoneLayer

    default_origin = b'http://janux.ou.edu'

    assignments_path = '/dataserver2/%2B%2Betc%2B%2Bhostsites/platform.ou.edu/%2B%2Betc%2B%2Bsite/Courses/Fall2013/CLC3403_LawAndJustice/AssignmentsByOutlineNode'

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_link(self):
        instructor_environ = self._make_extra_environ(username='harp4162')
        res = self.testapp.get(self.assignments_path,
                               extra_environ=instructor_environ)

        assignment = res.json_body.get('Items')[
            'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.sec:QUIZ_01.01'][0]
        self.forbid_link_with_rel(
            assignment, 'report-' + VIEW_ASSIGNMENT_SUMMARY)

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_application_view_report(self):
        instructor_environ = self._make_extra_environ(username='harp4162')
        res = self.testapp.get(self.assignments_path,
                               extra_environ=instructor_environ)

        # No link with no submissions
        assignment = res.json_body.get('Items')[
            'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.sec:QUIZ_01.01'][0]
        assignment_href = assignment.get('href')
        self.forbid_link_with_rel(
            assignment, 'report-' + VIEW_ASSIGNMENT_SUMMARY)

        # Sends an assignment through the application by posting to the
        # assignment
        qs_submission = QuestionSetSubmission(
            questionSetId=self.question_set_id)
        submission = AssignmentSubmission(
            assignmentId=self.assignment_id, parts=(qs_submission,))

        ext_obj = to_external_object(submission)

        # Enroll and submit.
        self.testapp.post_json('/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
                               'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2013_CLC3403_LawAndJustice',
                               status=201)

        self.testapp.post_json(assignment_href, ext_obj)

        # Now we have proper link
        res = self.testapp.get(self.assignments_path,
                               extra_environ=instructor_environ)

        assignment = res.json_body.get('Items')[
            'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.sec:QUIZ_01.01'][0]
        report_href = self.require_link_href_with_rel(
            assignment, 'report-' + VIEW_ASSIGNMENT_SUMMARY)

        _require_link_with_title(assignment, "Assignment Summary Report")

        res = self.testapp.get(report_href, extra_environ=instructor_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

        # check admin role fetch report
        admin_environ = self._make_extra_environ(username='sjohnson@nextthought.com')
        res = self.testapp.get(report_href, extra_environ=admin_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

        # check site admin role fetch report
        self.testapp.post_json('/dataserver2/SiteAdmins/harp4162',
                               status=200)
        site_admin_environ = self._make_extra_environ(username='harp4162')
        res = self.testapp.get(report_href, extra_environ=site_admin_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))


class TestStudentParticipationCSV(ApplicationLayerTest):

    layer = RegisterAssignmentsForEveryoneLayer
    default_origin = b'http://janux.ou.edu'

    course_ntiid = 'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    @fudge.patch('nti.app.products.courseware_reports.views.admin_views.StudentParticipationCSVView._get_users_from_request',
                 'nti.app.products.courseware_reports.views.admin_views.StudentParticipationCSVView._get_all_videos',
                 'nti.app.analytics.usage_stats.UserCourseVideoUsageStats.get_stats',
                 'nti.app.products.courseware_reports.views.admin_views.StudentParticipationCSVView._get_grade_from_assignment',
                 'nti.app.products.courseware_reports.views.admin_views.get_course_assignments')
    def test_csv_results(self, fake_get_users, fake_get_videos,
                         fake_video_stats, fake_assignment_grade, fake_assignment_catalog):

        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):

            obj = find_object_with_ntiid(self.course_ntiid)
            course = ICourseInstance(obj)
            request = DummyRequest(params={})
            request.context = course

            video_ntiid = 'tag:nextthought.com,2011-10:OU-NTIVideo-CLC3403_LawAndJustice.ntivideo.video_02.01'
            video_ntiid_2 = 'tag:nextthought.com,2011-10:OU-NTIVideo-CLC3403_LawAndJustice.ntivideo.video_02.02'

            fake_get_users.is_callable().returns([
                User.get_user('sjohnson@nextthought.com')])

            fake_video_1 = fudge.Fake().has_attr(
                title='fake video title 1', ntiid=video_ntiid)
            fake_video_2 = fudge.Fake().has_attr(
                title='fake video title 2', ntiid=video_ntiid_2)

            fake_get_videos.is_callable().returns([fake_video_1, fake_video_2])

            fake_video_stats.is_callable().returns((_VideoInfo('fake video title 1',
                                                               video_ntiid,
                                                               2,
                                                               3,
                                                               _AverageWatchTimes(
                                                                   '1:30', '2:30'),
                                                               '3:30',
                                                               '100',
                                                               1,
                                                               None),
                                                    _VideoInfo('fake video title 2',
                                                               video_ntiid_2,
                                                               4,
                                                               5,
                                                               _AverageWatchTimes(
                                                                   '5:30', '8:30'),
                                                               '5:30',
                                                               '100',
                                                               1,
                                                               None),))

            fake_assignment_1 = fudge.Fake().has_attr(
                title='fake assignment 1', grade=100)
            fake_assignment_2 = fudge.Fake().has_attr(
                title='fake assignment 2', grade=67)
            fake_assignment_catalog.is_callable().returns(
                [fake_assignment_1, fake_assignment_2])
            fake_assignment_grade.is_callable().calls(
                self._fake_get_grade_from_assignment)

            csv_view = StudentParticipationCSVView(request)
            response = csv_view()

            csv_read_buffer = StringIO(response.body)
            response_reader = csv.DictReader(csv_read_buffer)

            # We are using dict reader, so we can just check that
            # the keys have the correct values. If the CSV was
            # misaligned, these values would be incorrect.

            response_rows = [row for row in response_reader]
            assert_that(response_rows, has_item(
                has_entries('username', 'sjohnson@nextthought.com',
                            '[VideoViewCount] fake video title 1', '3',
                            '[VideoCompleted] fake video title 1', 'Completed',
                            '[VideoViewCount] fake video title 2', '5',
                            '[VideoCompleted] fake video title 2', 'Completed',
                            '[AssignmentGrade] fake assignment 1', '100',
                            '[AssignmentGrade] fake assignment 2', '67')))

            # TODO: add tests for self-assessments

    def _fake_get_grade_from_assignment(self, assignment, user_histories):
        return assignment.grade

class TestUserEnrollmentReport(ApplicationLayerTest):

    layer = InstructedCourseApplicationTestLayer
    default_origin = b'http://janux.ou.edu'
    course_ntiid = 'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'
    fetch_user_url = '/dataserver2/ResolveUser/'
    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_application_view_empty_report(self):

        self.testapp.post_json('/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
                               'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2013_CLC3403_LawAndJustice',
                               status=201)

        # user fetch themselves
        user_environ = self._make_extra_environ(username='sjohnson@nextthought.com')
        admin_fetch = self.testapp.get(self.fetch_user_url + 'sjohnson@nextthought.com',
                                       extra_environ=user_environ)

        report_links = admin_fetch.json_body.get(
            'Items')[0]

        admin_view_href = self.require_link_href_with_rel(report_links,
                                                    'report-%s' % VIEW_USER_ENROLLMENT)

        _require_link_with_title(report_links, "User Enrollment Report")

        res = self.testapp.get(admin_view_href, extra_environ=user_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

        # other users fetch user
        instructor_environ = self._make_extra_environ(username='harp4162')
        admin_fetch = self.testapp.get(self.fetch_user_url + 'sjohnson@nextthought.com',
                                         extra_environ=instructor_environ)

        report_links = admin_fetch.json_body.get(
            'Items')[0]

        view_href = self.link_href_with_rel(report_links,
                                            'report-%s' % VIEW_USER_ENROLLMENT)

        assert_that(view_href,
                    described_as("A link with rel %0", is_(none()), 'report-%s' % VIEW_USER_ENROLLMENT))

        # site-admin fetch report
        self.testapp.post_json('/dataserver2/SiteAdmins/harp4162',
                               status=200)
        site_admin_environ = self._make_extra_environ(username='harp4162')
        res = self.testapp.get(admin_view_href, extra_environ=site_admin_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

    @WithSharedApplicationMockDS(
                users=True, testapp=True, default_authenticate=True)
    @fudge.patch('nti.app.products.courseware_reports.views.user_views.UserEnrollmentReportPdf._check_access')
    def test_report_completion_data_no_enrolled(self, fake_check_access):
        fake_check_access.is_callable().returns(True)

        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            context = User.get_user('sjohnson@nextthought.com')
            request = DummyRequest(params={})
            request.params['remoteUser'] = User.get_user('harp4162')
            user_enrollment_report = UserEnrollmentReportPdf(
                context, request)

            options = user_enrollment_report()

            assert_that(options, has_key('user'))
            assert_that(options, has_key('enrollments'))
            assert_that(options['enrollments'], has_length(0))

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    @fudge.patch('nti.app.products.courseware_reports.views.user_views.UserEnrollmentReportPdf._check_access')
    def test_report_completion_data_enrolled(self, fake_check_access):
        self.testapp.post_json('/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
                               'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2013_CLC3403_LawAndJustice',
                               status=201)

        fake_check_access.is_callable().returns(True)

        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            context = User.get_user('sjohnson@nextthought.com')
            request = DummyRequest(params={})
            request.params['remoteUser'] = User.get_user('harp4162')
            user_enrollment_report_enrolled = UserEnrollmentReportPdf(
                context, request)

            options = user_enrollment_report_enrolled()

            assert_that(options, has_key('user'))
            assert_that(options, has_entry('enrollments',
                                                       has_items(
                                                           has_key('title'),
                                                           has_key('createdTime'))))
            assert_that(options['enrollments'], has_length(1))

class TestCourseRosterReport(ApplicationLayerTest):

    layer = InstructedCourseApplicationTestLayer
    default_origin = b'http://janux.ou.edu'
    course_ntiid = 'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    def test_application_view_empty_report(self):
        def report_with_rel(ext_obj, rel):
            for lnk in ext_obj.get('Reports', ()):
                if lnk['rel'] == rel:
                    if lnk['href']:
                        return lnk['href']

        # check admin can fetch report
        instructor_environ = self._make_extra_environ(username='sjohnson@nextthought.com')
        admin_courses = self.testapp.get('/dataserver2/users/sjohnson@nextthought.com/Courses/AdministeredCourses/',
                                         extra_environ=instructor_environ)

        course_instance = admin_courses.json_body.get(
            'Items')[0].get('CourseInstance')

        admin_view_href = report_with_rel(
            course_instance, 'report-%s' % VIEW_COURSE_ROSTER)

        _require_report_with_title(course_instance, "Course Roster Report")

        res = self.testapp.get(admin_view_href, extra_environ=instructor_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

        # check others user can fetch report
        instructor_environ = self._make_extra_environ(username='harp4162')
        admin_courses = self.testapp.get('/dataserver2/users/harp4162/Courses/AdministeredCourses/',
                                         extra_environ=instructor_environ)

        course_instance = admin_courses.json_body.get(
                                                    'Items')[0].get('CourseInstance')

        admin_view_href = report_with_rel(course_instance, 'report-%s' % VIEW_COURSE_ROSTER)

        _require_report_with_title(course_instance, "Course Roster Report")

        self.testapp.get(admin_view_href, extra_environ=instructor_environ)

        # site-admin fetch report
        self.testapp.post_json('/dataserver2/SiteAdmins/harp4162',
                               status=200)
        site_admin_environ = self._make_extra_environ(username='harp4162')
        res = self.testapp.get(admin_view_href, extra_environ=site_admin_environ)
        assert_that(res, has_property('content_type', 'application/pdf'))

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    @fudge.patch('nti.app.products.courseware_reports.views.course_roster_views.CourseRosterReportPdf._check_access')
    def test_report_completion_data_no_enrolled(self, fake_check_access):
        fake_check_access.is_callable().returns(True)

        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            obj = find_object_with_ntiid(self.course_ntiid)

            context = ICourseInstance(obj)

            request = DummyRequest(params={})
            request.params['remoteUser'] = User.get_user('sjohnson@nextthought.com')

            course_roster_report = CourseRosterReportPdf(
                context, request)

            options = course_roster_report()

            assert_that(options,
                        has_entries(
                                    'enrollments', [],
                                    'TotalEnrolledCount', 0))

    @WithSharedApplicationMockDS(
        users=True, testapp=True, default_authenticate=True)
    @fudge.patch('nti.app.products.courseware_reports.views.course_roster_views.CourseRosterReportPdf._check_access')
    def test_report_completion_data_enrolled(self, fake_check_access):
        fake_check_access.is_callable().returns(True)

        self.testapp.post_json('/dataserver2/users/sjohnson@nextthought.com/Courses/EnrolledCourses',
                               'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2013_CLC3403_LawAndJustice',
                               status=201)

        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            obj = find_object_with_ntiid(self.course_ntiid)

            context = ICourseInstance(obj)

            request = DummyRequest(params={})
            request.params['remoteUser'] = User.get_user('sjohnson@nextthought.com')

            course_roster_report = CourseRosterReportPdf(
                context, request)

            options = course_roster_report()

            assert_that(
                        options, has_entries('enrollments', has_items(
                                                                    has_key('displayname'),
                                                                    has_key('realname'),
                                                                    has_key('username'),
                                                                    has_key('email'),
                                                                    has_key('enrollmentTime'),
                                                                    has_key('lastAccessed'))))

            assert_that(options['enrollments'], has_length(1))
            assert_that(options['TotalEnrolledCount'], equal_to(1))

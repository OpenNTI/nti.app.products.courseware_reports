#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import is_not
from hamcrest import equal_to
from hamcrest import has_item
from hamcrest import not_none
from hamcrest import has_entry
from hamcrest import assert_that
from hamcrest import has_entries
from hamcrest import contains_inanyorder
does_not = is_not

import json

from zope import component

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.app.products.courseware_reports.reports import InstructorReport

from nti.app.products.courseware.tests import PersistentInstructedCourseApplicationTestLayer

from nti.app.testing.decorators import WithSharedApplicationMockDS

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseEnrollmentManager

from nti.contenttypes.reports.reports import evaluate_permission

from nti.dataserver.tests import mock_dataserver

from nti.dataserver.users.users import User

from nti.externalization.externalization import to_external_object
from nti.externalization.interfaces import StandardExternalFields

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.app.products.courseware_reports.tests import ReportsLayerTest

CLASS = StandardExternalFields.CLASS
ITEMS = StandardExternalFields.ITEMS


class TestInstructorReport(ReportsLayerTest):
    """
    Test the permissions on an instructor report
    """

    layer = PersistentInstructedCourseApplicationTestLayer

    course_ntiid = u'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'

    instructor_username = u"harp4162"

    student_username = u'student001'

    admin_username = u"sjohnson@nextthought.com"

    default_origin = 'http://janux.ou.edu'

    @WithSharedApplicationMockDS(testapp=True, users=True, default_authenticate=True)
    def test_instructor_permissions(self):
        """
        Test that only instructors can access instructor reports
        """

        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            course_obj = find_object_with_ntiid(self.course_ntiid)
            course_instance_obj = ICourseInstance(course_obj)

            ins_user_obj = User.get_user(self.instructor_username)
            stu_user_obj = User.get_user(self.student_username)
            admin_user_obj = User.get_user(self.admin_username)

            reports = component.subscribers(
                (course_instance_obj,), IInstructorReport)

            assert_that(reports, not_none())

            ins_perm = evaluate_permission(reports[0],
                                           course_instance_obj, ins_user_obj)
            stu_perm = evaluate_permission(reports[0],
                                           course_instance_obj, stu_user_obj)
            admin_perm = evaluate_permission(reports[0],
                                             course_instance_obj, admin_user_obj)

            assert_that(ins_perm, equal_to(True))
            assert_that(stu_perm, equal_to(False))
            assert_that(admin_perm, equal_to(True))

    @WithSharedApplicationMockDS(testapp=True, users=True, default_authenticate=True)
    def test_instructor_decoration(self):
        """
        Test that instructor report links are decorated correctly
        """
        with mock_dataserver.mock_db_trans(self.ds):
            self._create_user(username='test_instructor_decoration')

        instructor_environ = self._make_extra_environ(username='harp4162')
        admin_courses = self.testapp.get('/dataserver2/users/harp4162/Courses/AdministeredCourses/',
                                         extra_environ=instructor_environ)

        response_dict = json.loads(admin_courses.body)

        assert_that(response_dict, has_entry("Items", not_none()))
        entry_res = response_dict["Items"][0]
        course_rel = self.require_link_href_with_rel(entry_res, 'CourseInstance')
        course_res = self.testapp.get(course_rel, extra_environ=instructor_environ)
        course_res = course_res.json_body

        assert_that(course_res,
                    has_entry("Links",
                              does_not(has_item(has_entry("rel", "report-AnotherTestReport")))))

        # Now enroll and re-check
        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            course_obj = find_object_with_ntiid(self.course_ntiid)
            course_instance_obj = ICourseInstance(course_obj)
            user = User.get_user('test_instructor_decoration')
            enrollment_manager = ICourseEnrollmentManager(course_instance_obj)
            enrollment_manager.enroll(user)

        course_res = self.testapp.get(course_rel, extra_environ=instructor_environ)
        course_res = course_res.json_body

        assert_that(course_res,
                    has_entry("Links",
                              has_item(has_entry("rel", "report-AnotherTestReport"))))

    def test_instructor_externalization(self):
        """
        Test that instructor reports are externalized correctly
        """

        report = InstructorReport(name=u"Test",
                                  title=u"Test",
                                  description=u"TestDescription",
                                  contexts=(ICourseInstance,),
                                  supported_types=[u"csv", u"pdf"])

        ext_obj = to_external_object(report)

        assert_that(ext_obj,
                    has_entries(CLASS, "InstructorReport",
                                "name", "Test",
                                "title", "Test",
                                "description", "TestDescription",
                                "contexts", has_entry(ITEMS,
                                                      contains_inanyorder(ICourseInstance.__name__)),
                                "permission", equal_to(None),
                                "supported_types", contains_inanyorder("csv", "pdf")))

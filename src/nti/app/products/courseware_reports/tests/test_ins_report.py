#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904


from hamcrest import not_none
from hamcrest import equal_to
from hamcrest import has_item
from hamcrest import has_entry
from hamcrest import not_none
from hamcrest import assert_that
from hamcrest import has_entries
from hamcrest import contains_inanyorder

import functools

import json

from zope import component

from zope.component import getGlobalSiteManager

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.app.products.courseware_reports.reports import InstructorReport

from nti.app.products.courseware.tests import PersistentInstructedCourseApplicationTestLayer

from nti.app.testing.application_webtest import ApplicationLayerTest

from nti.app.testing.decorators import WithSharedApplicationMockDS

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.contenttypes.reports.reports import evaluate_permission

from nti.dataserver.tests import mock_dataserver

from nti.dataserver.users.users import User

from nti.externalization.externalization import to_external_object
from nti.externalization.externalization import StandardExternalFields

from nti.ntiids.ntiids import find_object_with_ntiid

CLASS = StandardExternalFields.CLASS


class TestInstructorReport(ApplicationLayerTest):
    """
    Test the permissions on an instructor report
    """

    layer = PersistentInstructedCourseApplicationTestLayer
    
    course_ntiid = u'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'
    
    instructor_username = u"harp4162"
    
    student_username = u"sjohnson@nextthought.com"

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

            self._register_report(u"TestReport",
                                  u"Test Report",
                                  u"TestDescription",
                                  ICourseInstance,
                                  [u"csv", u"pdf"])

            reports = component.subscribers(
                (course_instance_obj,), IInstructorReport)

            assert_that(reports, not_none())

            ins_perm = evaluate_permission(reports[0], 
                                           course_instance_obj, ins_user_obj)
            stu_perm = evaluate_permission(reports[0], 
                                           course_instance_obj, stu_user_obj)

            assert_that(ins_perm, equal_to(True))
            assert_that(stu_perm, equal_to(False))

    @WithSharedApplicationMockDS(testapp=True, users=True, default_authenticate=True)
    def test_instructor_decoration(self):
        """
        Test that instructor report links are 
        decorated correctly
        """
        self._register_report(u"AnotherTestReport",
                              u"Another Test Report",
                              u"AnotherTestDescription",
                              ICourseInstance,
                              [u"csv", u"pdf"])

        instructor_environ = self._make_extra_environ(username='harp4162')
        admin_courses = self.testapp.get('/dataserver2/users/harp4162/Courses/AdministeredCourses/',
                                         extra_environ=instructor_environ)

        response_dict = json.loads(admin_courses.body)

        assert_that(response_dict, has_entry("Items", not_none()))
        assert_that(response_dict["Items"],
                    has_item(has_entry("CourseInstance", not_none())))

        assert_that(response_dict["Items"][0]["CourseInstance"], 
                    has_entry("Links",
                              has_item(has_entry("rel", "report-AnotherTestReport"))))

    def test_instructor_externalization(self):
        """
        Test that instructor reports are externalized correctly
        """

        report = InstructorReport(name=u"Test",
                                  title=u"Test",
                                  description=u"TestDescription",
                                  interface_context=ICourseInstance,
                                  supported_types=[u"csv", u"pdf"])
        
        ext_obj = to_external_object(report)

        assert_that(ext_obj,
                    has_entries(CLASS, "InstructorReport",
                                "name", "Test",
                                "title", "Test",
                                "description", "TestDescription",
                                "interface_context", has_entry(CLASS,
                                                               ICourseInstance.__name__),
                                "permission", equal_to(None),
                                "supported_types", contains_inanyorder("csv", "pdf")))

    def _register_report(self, name, title, description,
                         interface_context, supported_types):
        """
        Register a temp report
        """
        report = functools.partial(InstructorReport,
                                   name=name,
                                   title=title,
                                   description=description,
                                   interface_context=interface_context,
                                   supported_types=supported_types)

        getGlobalSiteManager().registerSubscriptionAdapter(report,
                                                           (interface_context,),
                                                           IInstructorReport)

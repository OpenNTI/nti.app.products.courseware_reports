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
from hamcrest import has_length
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

    # Course ntiid
    course_ntiid = u'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'

    # Known instructor for the above course
    instructor_username = u"harp4162"

    # Student username
    student_username = u"sjohnson@nextthought.com"

    default_origin = 'http://janux.ou.edu'

    @WithSharedApplicationMockDS(testapp=True, users=True, default_authenticate=True)
    def test_instructor_permissions(self):

        # Open transaction to test the permissions
        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            # Get the course
            course_obj = find_object_with_ntiid(self.course_ntiid)
            course_instance_obj = ICourseInstance(course_obj)

            # Get the user objects
            ins_user_obj = User.get_user(self.instructor_username)
            stu_user_obj = User.get_user(self.student_username)

            # Register the test report
            self._register_report(u"TestReport",
                                  u"TestDescription",
                                  ICourseInstance,
                                  [u"csv", u"pdf"])

            # Get the report
            reports = component.subscribers(
                (course_instance_obj,), IInstructorReport)

            # We actually have the two registered from
            # both test cases, so we should have two.
            assert_that(reports, has_length(2))

            # Evaluate the permissions on both reports
            ins_perm = evaluate_permission(reports[0], 
                                           course_instance_obj, ins_user_obj)
            stu_perm = evaluate_permission(reports[0], 
                                           course_instance_obj, stu_user_obj)

            # Be sure the values we received are correct
            assert_that(ins_perm, equal_to(True))
            assert_that(stu_perm, equal_to(False))

    @WithSharedApplicationMockDS(testapp=True, users=True, default_authenticate=True)
    def test_instructor_decoration(self):
        # Register the test report
        self._register_report(u"AnotherTestReport",
                              u"AnotherTestDescription",
                              ICourseInstance,
                              [u"csv", u"pdf"])

        # Pull some courses to make sure a course was decorated correctly
        instructor_environ = self._make_extra_environ(username='harp4162')
        admin_courses = self.testapp.get('/dataserver2/users/harp4162/Courses/AdministeredCourses/',
                                         extra_environ=instructor_environ)

        # Turn the json into a dict
        response_dict = json.loads(admin_courses.body)

        # Be sure course has all of the relevant items where
        # the link should be
        assert_that(response_dict, has_entry("Items", not_none()))
        assert_that(response_dict["Items"],
                    has_item(has_entry("CourseInstance", not_none())))

        # Be sure the link came our correctly
        assert_that(response_dict["Items"][0]["CourseInstance"], 
                    has_entry("Links",
                              has_item(has_entry("rel", "report-AnotherTestReport"))))

    def test_instructor_externalization(self):

        # Create test report
        report = InstructorReport(name=u"Test",
                                  description=u"TestDescription",
                                  interface_context=ICourseInstance,
                                  permission=None,
                                  supported_types=[u"csv", u"pdf"])

        # Externalize the object
        ext_obj = to_external_object(report)

        # Be sure that the external object has the right specs
        assert_that(ext_obj,
                    has_entries(CLASS, "InstructorReport",
                                "name", "Test",
                                "description", "TestDescription",
                                "interface_context", has_entry(CLASS,
                                                               ICourseInstance.__name__),
                                "permission", equal_to(None),
                                "supported_types", contains_inanyorder("csv", "pdf")))

    def _register_report(self, name, description,
                         interface_context, supported_types):
        # Build a report factory
        report = functools.partial(InstructorReport,
                                   name=name,
                                   description=description,
                                   interface_context=interface_context,
                                   permission=None,
                                   supported_types=supported_types)

        # Register it as a subscriber
        getGlobalSiteManager().registerSubscriptionAdapter(report,
                                                           (interface_context,),
                                                           IInstructorReport)

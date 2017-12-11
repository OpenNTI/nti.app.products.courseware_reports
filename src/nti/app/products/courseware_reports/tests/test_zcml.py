#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import has_item
from hamcrest import not_none
from hamcrest import assert_that
from hamcrest import has_properties
from hamcrest import contains_inanyorder

import unittest

from zope import component
from zope import interface

from zope.component.hooks import setHooks

from zope.configuration import config
from zope.configuration import xmlconfig

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.contenttypes.reports.interfaces import IReport

from nti.contenttypes.reports.tests import ITestReportContext

from nti.testing.base import AbstractTestBase

# Example ZCML file that would call the registerReport directive
HEAD_ZCML_STRING = u"""
<configure  xmlns="http://namespaces.zope.org/zope"
            xmlns:i18n="http://namespaces.zope.org/i18n"
            xmlns:zcml="http://namespaces.zope.org/zcml"
            xmlns:rep="http://nextthought.com/reports">

    <include package="zope.component" file="meta.zcml" />
    <include package="zope.security" file="meta.zcml" />
    <include package="zope.component" />
    <include package="." file="meta.zcml"/>
    <include package="zope.vocabularyregistry" />

    <configure>
        <rep:registerInstructorReport name="TestReport"
                            title="Test Report"
                            description="TestDescription"
                            contexts="nti.contenttypes.reports.tests.ITestReportContext"
                            supported_types="csv pdf" />
    </configure>
</configure>
"""


@interface.implementer(ITestReportContext)
class TestReportContext(object):
    pass


class TestZcml(unittest.TestCase):

    get_config_package = AbstractTestBase.get_configuration_package.__func__

    def setUp(self):
        super(TestZcml, self).setUp()
        setHooks()

    def test_zcml(self):
        # Using the above ZCML string, set up the temporary configuration and run the string
        # through ZCML processor
        context = config.ConfigurationMachine()
        context.package = self.get_config_package()
        xmlconfig.registerCommonDirectives(context)
        xmlconfig.string(HEAD_ZCML_STRING, context)

        # Build test object
        test_context = TestReportContext()

        # Get all subscribers that are registered to an IReport object
        reports = component.subscribers((test_context,), IInstructorReport)

        # Be sure that the subscriber we ended up with matches the test registration in the
        # sample ZCML
        assert_that(reports, not_none())
        assert_that(reports, has_item(has_properties("name", "TestReport",
                                                     "title", "Test Report",
                                                     "contexts", not_none(),
                                                     "description", "TestDescription",
                                                     "contexts", not_none(),
                                                     "supported_types", contains_inanyorder("pdf", "csv"))))

        ut_reports = list(component.getAllUtilitiesRegisteredFor(IReport))
        assert_that(ut_reports, not_none())
        assert_that(reports, has_item(has_properties("name", "TestReport",
                                                     "title", "Test Report",
                                                     "contexts", not_none(),
                                                     "description", "TestDescription",
                                                     "contexts", not_none(),
                                                     "supported_types", contains_inanyorder("pdf", "csv"))))

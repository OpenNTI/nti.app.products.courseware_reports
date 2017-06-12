#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

import functools

import zope

import zope.testing

from zope import component

from zope.component import getGlobalSiteManager

from nti.analytics.database.interfaces import IAnalyticsDB
from nti.analytics.database.database import AnalyticsDB

from nti.app.products.courseware_reports.reports import InstructorReport

from nti.app.products.courseware_reports.interfaces import IInstructorReport

from nti.app.testing.application_webtest import ApplicationLayerTest

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.contenttypes.reports.reports import DefaultReportLinkProvider

from nti.testing.base import AbstractTestBase


class ReportsLayerTest(ApplicationLayerTest):

    utils = []
    factory = None

    @classmethod
    def setUp(self):
        """
        Set up environment for app layer report testing
        """
        self.db = AnalyticsDB(dburi='sqlite://')
        component.getGlobalSiteManager().registerUtility(self.db, IAnalyticsDB)

        def _register_report(name, title, description,
                             contexts, supported_types):
            """
            Manual and temporary registration of reports
            """

            # Build a report factory
            report = functools.partial(InstructorReport,
                                       name=name,
                                       title=title,
                                       description=description,
                                       contexts=contexts,
                                       supported_types=supported_types,
                                       link_provider=DefaultReportLinkProvider)
            self.factory = report

            report_obj = report()
            # Register as a utility
            getGlobalSiteManager().registerUtility(report_obj, IInstructorReport, name)

            for interface in contexts:
                # Register it as a subscriber
                getGlobalSiteManager().registerSubscriptionAdapter(report,
                                                                   (interface,),
                                                                   IInstructorReport)

            return report_obj

        # Register three reports to test with
        self.utils.append(_register_report(u"TestReport",
                                           u"Test Report",
                                           u"TestDescription",
                                           (ICourseInstance,),
                                           [u"csv", u"pdf"]))

        self.utils.append(_register_report(u"AnotherTestReport",
                                           u"Another Test Report",
                                           u"AnotherTestDescription",
                                           (ICourseInstance,),
                                           [u"csv", u"pdf"]))

        self.utils.append(_register_report(u"ThirdTestReport",
                                           u"Third Test Report",
                                           u"ThirdTestDescription",
                                           (ICourseInstance,),
                                           [u"csv", u"pdf"]))

    @classmethod
    def tearDown(self):
        """
        Unregister all test utilities and
        subscribers
        """
        sm = component.getGlobalSiteManager()
        sm.unregisterUtility(self.db)
        for util in self.utils:
            sm.unregisterUtility(
                component=util,
                provided=IInstructorReport,
                name=util.name)
        sm.unregisterSubscriptionAdapter(
            factory=self.factory, required=(
                ICourseInstance,), provided=IInstructorReport)

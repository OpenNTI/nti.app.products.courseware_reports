#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import is_
from hamcrest import contains
from hamcrest import not_none
from hamcrest import has_entry
from hamcrest import assert_that
from hamcrest import has_property

import fudge
import unittest

from nti.app.products.courseware_reports import VIEW_ASSIGNMENT_SUMMARY
from nti.app.products.courseware_reports import VIEW_FORUM_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_TOPIC_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_STUDENT_PARTICIPATION
from nti.app.products.courseware_reports import VIEW_SELF_ASSESSMENT_SUMMARY

from nti.app.products.courseware_reports.decorators import _AssignmentSummaryReport
from nti.app.products.courseware_reports.decorators import _ForumParticipationReport
from nti.app.products.courseware_reports.decorators import _TopicParticipationReport
from nti.app.products.courseware_reports.decorators import _StudentParticipationReport
from nti.app.products.courseware_reports.decorators import _SelfAssessmentSummaryReport

class TestDecorators(unittest.TestCase):

    def test_student_participation_decorator(self):
        spr = _StudentParticipationReport(object(), None)
        result = {}
        spr._do_decorate_external(object(), result)
 
        assert(result is not None)
        assert_that(result, is_(not_none()))
 
        assert_that(result, has_entry('Links',
                                contains(has_property('rel', 'report-%s' % VIEW_STUDENT_PARTICIPATION))))

    def test_forum_participation_decorator(self):
        spr = _ForumParticipationReport(object(), None)
        result = {}
        spr._do_decorate_external(object(), result)

        assert(result is not None)
        assert_that(result, is_(not_none()))

        assert_that(result, has_entry('Links',
                                contains(has_property('rel', 'report-%s' % VIEW_FORUM_PARTICIPATION))))

    def test_topic_participation_decorator(self):
        spr = _TopicParticipationReport(object(), None)
        result = {}
        spr._do_decorate_external(object(), result)

        assert(result is not None)
        assert_that(result, is_(not_none()))

        assert_that(result, has_entry('Links',
                                contains(has_property('rel', 'report-%s' % VIEW_TOPIC_PARTICIPATION))))

    def test_self_assessment_summary_decorator(self):
        spr = _SelfAssessmentSummaryReport(object(), None)
        result = {}
        spr._do_decorate_external(object(), result)

        assert(result is not None)
        assert_that(result, is_(not_none()))

        assert_that(result, has_entry('Links',
                                contains(has_property('rel', 'report-%s' % VIEW_SELF_ASSESSMENT_SUMMARY))))

    @fudge.patch('nti.app.products.courseware_reports.decorators._AssignmentSummaryReport._gradebook_entry')
    def test_assignment_history_decorator(self, mock_gradebook_entry):
        mock_gradebook_entry.is_callable().returns(object())
        spr = _AssignmentSummaryReport(object(), None)
        result = {}
        spr._do_decorate_external(object(), result)

        assert(result is not None)
        assert_that(result, is_(not_none()))

        assert_that(result, has_entry('Links',
                                contains(has_property('rel', 'report-%s' % VIEW_ASSIGNMENT_SUMMARY))))

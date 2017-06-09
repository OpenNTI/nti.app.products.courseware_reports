#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import zope.i18nmessageid
MessageFactory = zope.i18nmessageid.MessageFactory(__name__)

VIEW_INQUIRY_REPORT = 'InquiryReport.pdf'
VIEW_VIDEO_REPORT = "VideoUsageReport.pdf"
VIEW_COURSE_SUMMARY = "CourseSummaryReport.pdf"
VIEW_ASSIGNMENT_SUMMARY = 'AssignmentSummaryReport.pdf'
VIEW_FORUM_PARTICIPATION = "ForumParticipationReport.pdf"
VIEW_TOPIC_PARTICIPATION = "TopicParticipationReport.pdf"
VIEW_STUDENT_PARTICIPATION = "StudentParticipationReport.pdf"
VIEW_SELF_ASSESSMENT_SUMMARY = 'SelfAssessmentSummaryReport.pdf'

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
$Id$
"""
from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from pyramid.view import view_config

from nti.app.assessment.interfaces import ICourseAssignmentCatalog
from nti.app.assessment.interfaces import IUsersCourseAssignmentHistory
from nti.app.assessment.interfaces import get_course_assignment_predicate_for_user
from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment
from nti.app.products.gradebook.interfaces import IGrade
from nti.dataserver.interfaces import IUser

from nti.app.base.abstract_views import AbstractAuthenticatedView

from .interfaces import ACT_VIEW_REPORTS

@view_config(route_name='objects.generic.traversal',
			 context=ICourseInstanceEnrollment,
			 request_method='GET',
			 permission=ACT_VIEW_REPORTS,
			 name='StudentParticipationReport.pdf',
			 renderer="templates/StudentParticipationReport.rml")
class StudentParticipationReportPdf(AbstractAuthenticatedView):

	def __call_(self):
		course = self.context.CourseInstance
		student_user = IUser(self.context)
		# Collect data and return it in a form to be rendered
		# (a dictionary containing data and callable objects)

		# Graph of forum participation over time (time-series of forum-related
		# objects created bucketed by something--week?) probably a linePlot

		# Tabular breakdown of what topics the user created in what forum
		# and how many comments in which topics (could be bulkData or actual blockTable)

		# Each self-assessment and how many times taken (again bulkData)

		# Table of assignment history and grades for all assignments in course

		assignment_catalog = ICourseAssignmentCatalog(course)

		# TODO: Do we need to filter this?
		uber_filter = get_course_assignment_predicate_for_user(student_user, course)
		histories = IUsersCourseAssignmentHistory(course, student_user)
		return {}

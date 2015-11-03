#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from .. import MessageFactory as _

from pyramid.view import view_config

from nti.contenttypes.courses.interfaces import ICourseInstance

from .. import VIEW_SELF_ASSESSMENT_SUMMARY

from ..reports import _TopCreators
from ..reports import _StudentInfo

from .summary_views import CourseSummaryReportPdf

@view_config(context=ICourseInstance,
			 name=VIEW_SELF_ASSESSMENT_SUMMARY)
class SelfAssessmentSummaryReportPdf(CourseSummaryReportPdf):
	"""
	A basic SelfAssessment report for a course.  This is useful for
	ad-hoc reports requested by instructors, but no link is yet
	provided for client usage.
	"""

	report_title = _('Self Assessment Report')

	def _build_student_info(self, username):
		student_info = self.get_student_info( username )
		return _StudentInfo( 	student_info.display,
								student_info.username,
								0, 0 )

	def _get_self_assessments_by_student( self ):
		"""
		Get our sorted stats, including zero'd stats for users
		without self assessment submissions.
		"""
		stats = self.assessment_aggregator.all_stats
		assessment_usernames = {x.username.lower() for x in stats}
		missing_usernames = self.all_student_usernames - assessment_usernames
		stats.extend( (self._build_student_info( username )
						for username in missing_usernames) )
		return sorted( stats, key=lambda x:x.display.lower() )

	def __call__(self):
		self._check_access()
		options = self.options
		self.assessment_aggregator = _TopCreators(self)
		self._build_self_assessment_data( options )
		options['self_assessment_by_student'] = self._get_self_assessments_by_student()
		self._build_enrollment_info(options)
		return options

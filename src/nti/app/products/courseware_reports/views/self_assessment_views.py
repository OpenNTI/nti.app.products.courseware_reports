#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from collections import namedtuple

from nti.app.products.courseware_reports import MessageFactory as _

from pyramid.view import view_config

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.app.products.courseware_reports import VIEW_SELF_ASSESSMENT_SUMMARY

from nti.app.products.courseware_reports.reports import _TopCreators
from nti.app.products.courseware_reports.reports import _StudentInfo

from nti.app.products.courseware_reports.views.summary_views import CourseSummaryReportPdf

_SelfAssessmentCompletion = namedtuple( '_SelfAssessmentCompletion',
										('title', 'question_count', 'students'))

@view_config(context=ICourseInstance,
			 name=VIEW_SELF_ASSESSMENT_SUMMARY)
class SelfAssessmentSummaryReportPdf(CourseSummaryReportPdf):
	"""
	A basic SelfAssessment report for a course.  This is useful for
	ad-hoc reports requested by instructors, but no link is yet
	provided for client usage.
	"""

	report_title = _('Self Assessment Report')

	def _build_student_info(self, username, count=0, perc=0):
		student_info = self.get_student_info( username )
		return _StudentInfo( 	student_info.display,
								student_info.username,
								count,
								perc )

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

	def _build_qset_to_user_submission(self):
		# qset.ntiid -> username -> submitted question ntiid set
		qsid_to_user_submission_set = {}
		completed_sets = {}
		# Iterate through submission, gathering all question_ids with response.
		for submission in self._self_assessment_submissions:
			# Content may have changed such that we have an orphaned question set; move on.
			if submission.questionSetId in self._self_assessment_qsids:
				asm = self._self_assessment_qsids[submission.questionSetId]
				username = submission.creator.username.lower()
				if asm.ntiid in completed_sets.get( username, {} ):
					continue
				student_sets = qsid_to_user_submission_set.setdefault( asm.ntiid, {} )
				student_set = student_sets.setdefault( username, set() )
				completed = True
				for question in submission.questions:
					for part in question.parts:
						if part.submittedResponse:
							student_set.add( question.questionId )
						else:
							completed = False
				if completed:
					user_completed = completed_sets.setdefault( username, set() )
					user_completed.add( asm.ntiid )
		return qsid_to_user_submission_set

	def _get_self_assessments_completion(self):
		"""
		By self assessment, gather how many questions the student submitted to
		return completion stats.
		"""
		# qset.ntiid -> username -> submitted question ntiid set
		qsid_to_user_submission_set = self._build_qset_to_user_submission()

		result = list()
		# Now build our completion data.
		for asm in self._self_assessments:
			title = asm.title or asm.__parent__.title
			question_count = len( asm.questions )
			qset_submission_data = qsid_to_user_submission_set.get( asm.ntiid )
			students = []
			for username in self.all_student_usernames:
				submitted_count = len( qset_submission_data.get( username, () ))
				perc = "%0.1f" % (submitted_count/question_count * 100.0)
				student_info = self._build_student_info(username, submitted_count, perc)
				students.append( student_info )
			students = sorted( students, key=lambda x: x.display.lower() )
			completion = _SelfAssessmentCompletion( title, question_count, students )
			result.append( completion )
		result = sorted( result, key=lambda x: x.title )
		return result

	def __call__(self):
		self._check_access()
		options = self.options
		self.assessment_aggregator = _TopCreators(self)
		self._build_self_assessment_data( options )
		options['self_assessment_by_student'] = self._get_self_assessments_by_student()
		options['self_assessment_completion'] = self._get_self_assessments_completion()
		self._build_enrollment_info(options)
		return options

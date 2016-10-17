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

from nti.app.products.courseware_reports.views.summary_views import CourseSummaryReportPdf

_SelfAssessmentCompletion = namedtuple( '_SelfAssessmentCompletion',
										('title', 'question_count', 'students'))

@view_config(context=ICourseInstance,
			 name=VIEW_SELF_ASSESSMENT_SUMMARY)
class SelfAssessmentSummaryReportPdf(CourseSummaryReportPdf):
	"""
	A basic SelfAssessment report for a course, including
	summary data on overall self-assessment usage and per
	self-assessment completion data.
	"""

	report_title = _('Self Assessment Report')

	def _get_by_student_stats(self, stats, assessment_names, student_names):
		"""
		Get our sorted stats, including zero'd stats for users
		without self assessment submissions.
		"""
		assessment_usernames = {x.lower() for x in assessment_names}
		missing_usernames = student_names - assessment_usernames
		stats.extend( (self.build_user_info( username ) for username in missing_usernames) )
		stats = sorted( stats, key=lambda x:x.sorting_key.lower() )
		return stats

	def _get_self_assessments_by_student( self ):
		"""
		Get our by student stats for open and credit students.
		"""
		open_stats = self._get_by_student_stats( self.assessment_aggregator.open_stats,
												 self.assessment_aggregator.non_credit_keys(),
												 self.open_student_usernames )
		credit_stats = self._get_by_student_stats( self.assessment_aggregator.credit_stats,
												   self.assessment_aggregator.for_credit_keys(),
												   self.for_credit_student_usernames )
		return open_stats, credit_stats

	def _build_qset_to_user_submission(self):
		"""
		For each submission, gather the questions completed
		by each student.
		"""
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

	def _get_completion_student_data( self, submission_data, student_names, question_count ):
		"""
		Build out student infos from the given student population and submissions.
		"""
		results = []
		for username in student_names:
			submitted_count = len( submission_data.get( username, () ))
			perc = "%0.1f" % (submitted_count/question_count * 100.0) if question_count else 'NA'
			student_info = self.build_user_info(username, count=submitted_count, perc=perc)
			results.append( student_info )
		results = sorted( results, key=lambda x: x.sorting_key.lower() )
		return results

	def _get_self_assessments_completion(self):
		"""
		By self assessment, gather how many questions the student submitted to
		return completion stats.
		"""
		# qset.ntiid -> username -> submitted question ntiid set
		qsid_to_user_submission_set = self._build_qset_to_user_submission()

		credit_results = list()
		open_results = list()
		# Now build our completion data.
		for asm in self._self_assessments:
			title = asm.title or getattr( asm.__parent__, 'title', None )
			question_count = getattr( asm, 'draw', None ) or len( asm.questions )
			qset_submission_data = qsid_to_user_submission_set.get( asm.ntiid, {} )
			# Open
			open_students = self._get_completion_student_data( qset_submission_data,
															   self.open_student_usernames,
															   question_count )
			open_completion = _SelfAssessmentCompletion( title, question_count, open_students )
			open_results.append( open_completion )
			# Credit
			credit_students = self._get_completion_student_data( qset_submission_data,
																 self.for_credit_student_usernames,
																 question_count )
			credit_completion = _SelfAssessmentCompletion( title, question_count, credit_students )
			credit_results.append( credit_completion )
		open_results = sorted( open_results, key=lambda x: x.title )
		credit_results = sorted( credit_results, key=lambda x: x.title )
		return open_results, credit_results

	def __call__(self):
		self._check_access()
		options = self.options
		self.assessment_aggregator = _TopCreators(self)

		self._build_self_assessment_data( options )
		open_stats, credit_stats = self._get_self_assessments_by_student()
		options['self_assessment_non_credit'] = open_stats
		options['self_assessment_for_credit'] = credit_stats
		open_completion, credit_completion = self._get_self_assessments_completion()
		options['self_assessment_open_completion'] = open_completion
		options['self_assessment_credit_completion'] = credit_completion
		self._build_enrollment_info(options)
		return options

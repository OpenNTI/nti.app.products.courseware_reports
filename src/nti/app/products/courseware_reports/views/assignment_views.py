#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from .. import MessageFactory as _

from six import string_types
from docutils.utils import roman

from zope import component

from pyramid.view import view_config

from nti.app.assessment.interfaces import IUsersCourseAssignmentHistoryItem

from nti.app.products.gradebook.interfaces import IGradeBookEntry

from nti.assessment.common import grader_for_response

from nti.assessment.interfaces import IQAssignment
from nti.assessment.interfaces import IQMatchingPart
from nti.assessment.interfaces import IQMultipleChoicePart
from nti.assessment.interfaces import IQAssessedQuestionSet
from nti.assessment.interfaces import IQMultipleChoiceMultipleAnswerPart

from nti.assessment.randomized.interfaces import IQRandomizedPart

from nti.contentfragments.interfaces import IPlainTextContentFragment

from .. import VIEW_ASSIGNMENT_SUMMARY

from ..reports import _AnswerStat
from ..reports import _QuestionStat
from ..reports import _QuestionPartStat
from ..reports import _build_question_stats
from ..reports import _assignment_stat_for_column

from .view_mixins import _AbstractReportView

@view_config(context=IGradeBookEntry,
			 name=VIEW_ASSIGNMENT_SUMMARY)
class AssignmentSummaryReportPdf(_AbstractReportView):

	report_title = _('Assignment Summary Report')

	def _build_enrollment_info(self, options):
		options['count_for_credit'] = len(self.for_credit_student_usernames)
		options['count_open'] = len(self.open_student_usernames)
		options['count_total'] = options['count_for_credit'] + options['count_open']

	def _build_assignment_data(self, options):
		stats = [_assignment_stat_for_column(self, self.context)]
		options['assignment_data'] = stats

	def _build_question_data(self, options):
		assignment = component.queryUtility(IQAssignment, name=self.context.AssignmentId)
		if assignment is None:
			# Maybe this is something without an assignment, like Attendance?
			options['question_stats'] = None
			return

		# TODO Need to handle randomized questions.
		# - We might get this for free since we store our questions by ntiids.
		# - Verify.

		ordered_questions = []
		qids_to_q = {}
		for apart in assignment.parts:
			for q in apart.question_set.questions:
				ordered_questions.append(q)
				qids_to_q[q.ntiid] = q

		column = self.context
		question_stats = {}

		for grade in column.values():
			try:
				history = IUsersCourseAssignmentHistoryItem(grade)
			except TypeError:  # Deleted user
				continue

			submission = history.Submission

			for set_submission in submission.parts:
				for question_submission in set_submission.questions:

					question = qids_to_q[question_submission.questionId]

					question_stat = self._get_question_stat(question_stats,
																question_submission.questionId,
																question.parts)
					question_stat.submission_count += 1
					question_part_stats = question_stat.question_part_stats

					for idx in range(len(question.parts)):
						question_part = question.parts[idx]
						response = question_submission.parts[idx]
						answer_stat = question_part_stats[idx].answer_stats

						# Add to our responses.
						self._accumulate_response(question_part, response, submission, answer_stat)

			pending = history.pendingAssessment

			for maybe_assessed in pending.parts:
				if not IQAssessedQuestionSet.providedBy(maybe_assessed):
					continue
				for assessed_question in maybe_assessed.questions:
					for idx in range(len(assessed_question.parts)):

						assessed_part = assessed_question.parts[idx]
						val = assessed_part.assessedValue
						# We may not have a grade yet
						if val is not None:
							# We may have assessed values without submissions, perhaps due to weird alpha data.
							question_stat = self._get_question_stat(question_stats,
																	assessed_question.questionId,
																	assessed_question.parts)
							question_part_stats = question_stat.question_part_stats
							question_part_stats[idx].assessed_values.append(val)

		options['question_stats'] = _build_question_stats(ordered_questions, question_stats)

	def _get_question_stat(self, question_stats, question_id, parts):
		"""
		Retrieves question_stat for the given question, building if necessary
		"""
		if question_id in question_stats:
			question_stat = question_stats[ question_id ]
			question_part_stats = question_stat.question_part_stats
		else:
			question_part_stats = {}
			question_stats[ question_id ] = question_stat = _QuestionStat(question_part_stats)

		# make sure the data we always have the correct number of parts
		for idx in xrange(len(parts)):
			if idx not in question_part_stats:
				question_part_stats[idx] = _QuestionPartStat(roman.toRoman(idx + 1))

		return question_stat

	def _accumulate_response(self, question_part, response, submission, answer_stat):
		"""
		Adds the response information to our answer_stats
		"""
		if 		IQRandomizedPart.providedBy(question_part) \
			and response is not None:
			# First de-randomize our question part, if necessary.
			grader = grader_for_response(question_part, response)
			response = grader.unshuffle(response,
										user=submission.creator,
										context=question_part)

		if (IQMultipleChoicePart.providedBy(question_part)
			and not IQMultipleChoiceMultipleAnswerPart.providedBy(question_part)
			and isinstance(response, int)):
			# We have indexes into single multiple choice answers
			# convert int indexes into actual values
			self._add_multiple_choice_to_answer_stats(answer_stat,
													  response,
													  question_part,
													  lambda: response == question_part.solutions[0].value)
		elif (IQMultipleChoicePart.providedBy(question_part)
			and IQMultipleChoiceMultipleAnswerPart.providedBy(question_part)
			and response):
			# We are losing empty responses
			# The solutions should be int indexes, as well as our responses
			for r in response:
				self._add_multiple_choice_to_answer_stats(answer_stat,
														  r,
														  question_part,
														  lambda: r in question_part.solutions[0].value)
		elif isinstance(response, string_types):
			# IQFreeResponsePart?
			# Freeform answers
			response = response.lower()
			# In some cases, we have non-strings.
			solutions = (x.value.lower() if isinstance(x.value, string_types) else x
							for x in question_part.solutions)
			self._add_val_to_answer_stats(answer_stat,
											response,
											lambda: response in solutions)

		elif IQMatchingPart.providedBy(question_part) and response:
			# This handles both matching and ordering questions
			for key, val in response.items():
				val = int(val)  # Somehow, we have string vals stored in some cases
				left = question_part.labels[ int(key) ]
				left = self._get_displayable(left)

				right = question_part.values[val]
				right = self._get_displayable(right)

				content = (left, right)

				# Just need to check if our given key-value pair is in
				# the solution mappings
				check_correct = lambda: question_part.solutions[0].value[ key ] == val
				self._add_displayable_to_answer_stat(answer_stat,
														content,
														check_correct)
		elif response is None:
			# Unanswered questions get placed in our placeholder
			self._add_displayable_to_answer_stat(answer_stat,
													response,
													lambda: False)


	def _add_multiple_choice_to_answer_stats(self, answer_stat, response, question_part, check_correct):
		"""
		Adds the multiple choice response to our answer_stats
		"""
		try:
			response_val = question_part.choices[response]
		except (TypeError, IndexError):
			# Possibly here due to empty answers or stale, incorrect data
			response_val = ''
		self._add_val_to_answer_stats(answer_stat, response_val, check_correct)

	def _add_val_to_answer_stats(self, answer_stat, response, check_correct):
		"""
		Adds a response value to our answer_stats
		"""
		response = self._get_displayable(response)
		self._add_displayable_to_answer_stat(answer_stat, response, check_correct)

	def _add_displayable_to_answer_stat(self, answer_stat, response, check_correct):
		"""
		Adds a response value to our answer_stats
		"""
		if not response:
			# For empty strings, add a placeholder
			response = '[unanswered]'

		if response in answer_stat:
			answer_stat[response].count += 1
		else:
			is_correct = check_correct()
			answer_stat[response] = _AnswerStat(response, is_correct)

	def _get_displayable(self, source):
		if isinstance(source, string_types):
			source = IPlainTextContentFragment(source)
		return source

	def __call__(self):
		self._check_access()
		options = self.options
		self._build_enrollment_info(options)
		self._build_assignment_data(options)
		self._build_question_data(options)
		return options

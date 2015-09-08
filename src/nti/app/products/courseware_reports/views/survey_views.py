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

from zope import component

from pyramid.view import view_config

from nti.app.assessment.common import aggregate_course_inquiry

from nti.assessment.interfaces import IQSurvey

from nti.contentfragments.interfaces import IPlainTextContentFragment

from nti.contenttypes.courses.interfaces import ICourseInstance

from .. import VIEW_SURVEY_REPORT

from .view_mixins import _AbstractReportView

@view_config(context=IQSurvey,
			 name=VIEW_SURVEY_REPORT)
class SurveyReportPdf(_AbstractReportView):

	report_title = _('Survey Report')

	def _build_question_data(self, options):
		survey = component.queryUtility(IQSurvey, name=self.context.inquryId)
		if survey is None:
			options['question_stats'] = None
			return

		# TODO Need to handle randomized questions.
		# - We might get this for free since we store our questions by ntiids.
		# - Verify.
		course = component.queryMultiAdapter((self.context, self.remoteUser),
											  ICourseInstance)
		aggregate_course_inquiry(survey, course)

		# options['question_stats'] = _build_question_stats(ordered_questions, question_stats)

	def _get_displayable(self, source):
		if isinstance(source, string_types):
			source = IPlainTextContentFragment(source)
		return source

	def __call__(self):
		self._check_access()
		options = self.options
		self._build_question_data(options)
		return options
ICourseInstance
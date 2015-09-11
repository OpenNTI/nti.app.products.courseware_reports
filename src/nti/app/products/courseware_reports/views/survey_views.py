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
from pyramid import httpexceptions as hexc

from nti.app.assessment.common import aggregate_course_inquiry
from nti.app.assessment.interfaces import ICourseAggregatedInquiries

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
		options['question_stats'] = None
		course = component.queryMultiAdapter((self.context, self.remoteUser),
											  ICourseInstance)
		if course is None:
			raise hexc.HTTPUnprocessableEntity(_("Cannot find course for survey."))

		if self.context.closed:
			container = ICourseAggregatedInquiries(course)
			result = container[self.context.ntiid]
		else:
			result = aggregate_course_inquiry(self.context, course)
		return result
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

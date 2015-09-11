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
from nti.app.assessment.interfaces import ICourseAggregatedInquiries

from nti.assessment.interfaces import IQPoll
from nti.assessment.interfaces import IQSurvey

from nti.common.property import Lazy

from nti.contentfragments.interfaces import IPlainTextContentFragment

from nti.contenttypes.courses.interfaces import ICourseInstance

from .. import VIEW_SURVEY_REPORT

from .view_mixins import _AbstractReportView

@view_config(context=IQSurvey,
			 name=VIEW_SURVEY_REPORT)
class SurveyReportPdf(_AbstractReportView):

	report_title = _('Survey Report')

	@Lazy
	def course(self):
		course = component.getMultiAdapter((self.context, self.remoteUser),
											ICourseInstance)
		return course

	def _build_question_data(self, options):
		options['question_stats'] = None
		if self.context.closed:
			container = ICourseAggregatedInquiries(self.course)
			aggregated = container[self.context.ntiid]
		else:
			aggregated = aggregate_course_inquiry(self.context, self.course)
			
		for agg_poll in aggregated:
			poll = component.queryUtility(IQPoll, name=agg_poll.inquiryId)
			if poll is None: # pragma no cover
				continue
			for _, agg_part in enumerate(agg_poll):
				_ = agg_part.Results

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

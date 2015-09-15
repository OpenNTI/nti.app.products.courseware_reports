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
from nti.assessment.interfaces import IQNonGradableMultipleChoicePart
from nti.assessment.interfaces import IQNonGradableMultipleChoiceMultipleAnswerPart

from nti.common.property import alias, Lazy

from nti.contentfragments.interfaces import IPlainTextContentFragment

from nti.contenttypes.courses.interfaces import ICourseInstance

from .. import VIEW_SURVEY_REPORT

from .view_mixins import _AbstractReportView

class ResponseStat(object):

	def __init__(self, answer, count, percentage):
		self.count = count
		self.answer = answer
		self.percentage = percentage

class PollPartStat(object):

	kind = alias('type')
	
	def __init__(self, kind, content, responses=None):
		self.type = kind
		self.content = content
		self.responses = responses

class PollStat(object):

	parts = alias('poll_part_stats')

	def __init__(self, title, content, parts):
		self.title = title
		self.content = content
		self.poll_part_stats = parts if parts is not None else ()

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
		options['poll_stats'] = poll_stats = []

		if self.context.closed:
			container = ICourseAggregatedInquiries(self.course)
			aggregated = container[self.context.ntiid]
		else:
			aggregated = aggregate_course_inquiry(self.context, self.course)

		for idx, agg_poll in enumerate(aggregated):
			poll = component.queryUtility(IQPoll, name=agg_poll.inquiryId)
			if poll is None:  # pragma no cover
				continue

			title = idx + 1
			content = IPlainTextContentFragment(poll.content)
			if not content:
				content = IPlainTextContentFragment(poll.parts[0].content)

			poll_stat = PollStat(title, content, [])
			for idx, agg_part in enumerate(agg_poll):
				kind = 0
				responses = None
				part = poll[idx]
				total = agg_part.Total
				results = agg_part.Results
				
				if IQNonGradableMultipleChoiceMultipleAnswerPart.providedBy(part):
					pass
				elif IQNonGradableMultipleChoicePart.providedBy(part):
					kind = 1
					responses = []
					for idx, count in sorted(results.items()):
						response = ResponseStat(
										IPlainTextContentFragment(part.choices[idx]),
										count,
										(count / total)*100 if total else 0)
						responses.append(response)

				if responses:
					poll_stat.parts.append(
								PollPartStat(kind=kind,
											 content=IPlainTextContentFragment(part.content),
											 responses=responses))
			poll_stats.append(poll_stat)

	def _get_displayable(self, source):
		if isinstance(source, string_types):
			source = IPlainTextContentFragment(source)
		return source

	def __call__(self):
		self._check_access()
		options = self.options
		self._build_question_data(options)
		return options

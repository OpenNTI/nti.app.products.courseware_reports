#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import heapq

from .. import MessageFactory as _

from six import string_types

from zope import component

from pyramid.view import view_config

from nti.app.assessment.common import aggregate_course_inquiry
from nti.app.assessment.interfaces import ICourseAggregatedInquiries

from nti.assessment.interfaces import IQPoll
from nti.assessment.interfaces import IQSurvey
from nti.assessment.interfaces import IQNonGradableConnectingPart
from nti.assessment.interfaces import IQAggregatedFreeResponsePart
from nti.assessment.interfaces import IQNonGradableMultipleChoicePart
from nti.assessment.interfaces import IQNonGradableModeledContentPart
from nti.assessment.interfaces import IQNonGradableMultipleChoiceMultipleAnswerPart

from nti.common.property import alias, Lazy

from nti.contentfragments.interfaces import IPlainTextContentFragment

from nti.contenttypes.courses.interfaces import ICourseInstance

from .. import VIEW_SURVEY_REPORT

from .view_mixins import _AbstractReportView

class ResponseStat(object):

	answers = alias('answer')

	def __init__(self, answer, count, percentage):
		self.count = count
		self.answer = answer
		self.percentage = round(percentage,2) if percentage is not None else percentage

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

def plain_text(s):
	result = IPlainTextContentFragment(s) if s else u''
	return result.strip()

@view_config(context=IQSurvey,
			 name=VIEW_SURVEY_REPORT)
class SurveyReportPdf(_AbstractReportView):

	report_title = _('Survey Report')

	@Lazy
	def course(self):
		course = component.getMultiAdapter((self.context, self.remoteUser),
											ICourseInstance)
		return course

	def _get_response_stats(self, vals, total):
		# We expect a dict of answer to count
		# Only get our top 8 responses
		top_answer_stats = heapq.nlargest( 8, vals.items(), key=lambda x: x[1] )
		responses = []

		# Answer: (index,content) -> count
		for answer, count in top_answer_stats:
			response = ResponseStat(
							answer,
							count,
							(count / total) * 100 if total else 0)
			responses.append(response)
		return responses

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
			content = plain_text(poll.content)
			if not content:
				content = plain_text(poll.parts[0].content)

			poll_stat = PollStat(title, content, [])
			for idx, agg_part in enumerate(agg_poll):
				kind = 0
				responses = None
				part = poll[idx]
				total = agg_part.Total
				results = agg_part.Results

				if IQNonGradableConnectingPart.providedBy(part):
					kind = 3
					responses = []
					labels = part.labels
					values = part.values
					vals = {}

					# Group and count each submitted answer
					for tuples, count in sorted(results.items()):
						tuples = eval(tuples) if isinstance(tuples, string_types) else tuples

						for answer in tuples:
							answer  = (plain_text(labels[int(answer[0])]),
									plain_text(values[answer[1]]))
							if answer in vals:
								vals[answer] += count
							else:
								vals[answer] = 1

					# For ranking type responses, we probably don't want to
					# order by most common ranking, we probably want to rank
					# the top-ranked first (or only the top-ranked).  Or we
					# could allocate points per answer (more points for top-ranked)
					# and return that. Or we could return most common result sets.
					responses.extend( self._get_response_stats(vals, total) )
				elif IQNonGradableMultipleChoicePart.providedBy(part) or \
					 IQNonGradableMultipleChoiceMultipleAnswerPart.providedBy(part):
					kind = 1
					responses = []
					choices = part.choices
					for idx, count in sorted(results.items()):
						response = ResponseStat(
										plain_text(choices[int(idx)]),
										count,
										(count / total) * 100 if total else 0)
						responses.append(response)
				elif IQAggregatedFreeResponsePart.providedBy(part):
					kind = 1
					responses = []
					for text, count in sorted(results.items()):
						response = ResponseStat(
										plain_text(text),
										count,
										(count / total) * 100 if total else 0)
						responses.append(response)
				elif IQNonGradableModeledContentPart.providedBy( part ):
					kind = 4
					responses = []
					count = 0
					for text in results:
						if text:
							text = ' '.join( text )
						else:
							continue
						response = ResponseStat(
										text,
										count,
										(count / total) * 100 if total else 0)
						responses.append(response)

				if responses:
					poll_stat.parts.append(
								PollPartStat(kind=kind,
											 content=plain_text(part.content),
											 responses=responses))
			poll_stats.append(poll_stat)

	def _get_displayable(self, source):
		if isinstance(source, string_types):
			source = plain_text(source)
		return source

	def __call__(self):
		self._check_access()
		options = self.options
		self._build_question_data(options)
		return options

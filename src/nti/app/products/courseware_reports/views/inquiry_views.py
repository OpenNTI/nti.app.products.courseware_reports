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
from nti.app.assessment.common import inquiry_submissions

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

from nti.traversal.traversal import find_interface

from nti.app.products.courseware_reports import VIEW_INQUIRY_REPORT

from nti.app.products.courseware_reports.reports import _TopCreators

from nti.app.products.courseware_reports.utils import find_course_for_user

from nti.app.products.courseware_reports.views.view_mixins import _AbstractReportView

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

class InquiryReportPDF(_AbstractReportView):

	@Lazy
	def report_title(self):
		return u''

	@Lazy
	def course(self):
		course = find_interface(self.context, ICourseInstance, strict=False)
		if course is None:
			course = find_course_for_user(self.context, self.remoteUser)
		return course

	def _aggregated_polls(self, aggregated):
		raise NotImplementedError()

	def _build_question_data(self, options):
		options['poll_stats'] = poll_stats = []

		if self.context.closed:
			container = ICourseAggregatedInquiries(self.course)
			aggregated = container[self.context.ntiid]
		else:
			aggregated = aggregate_course_inquiry(self.context, self.course) or ()

		poll_stat_map = {}
		for idx, agg_poll in enumerate(self._aggregated_polls(aggregated)):
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
					mapped = {plain_text(labels[int(k)]):k for k in results.keys()}
					for label, k in sorted(mapped.items(), key=lambda x: x[0]):
						m = results.get(k)
						for v, count in sorted(m.items(), key=lambda x: x[1]):
							value = plain_text(values[int(v)])
							response = ResponseStat(
										(label, value),
										count,
										(count / total) * 100 if total else 0)
							responses.append(response)
				elif IQNonGradableMultipleChoicePart.providedBy(part) or \
					 IQNonGradableMultipleChoiceMultipleAnswerPart.providedBy(part):
					kind = 1
					responses = []
					choices = part.choices
					for idx, choice in enumerate(choices):
						count = results.get(idx) or results.get(str(idx)) or 0
						response = ResponseStat(
										plain_text(choice),
										count,
										(count / total) * 100 if total else 0)
						responses.append(response)
				elif IQAggregatedFreeResponsePart.providedBy(part):
					kind = 1
					responses = []
					for text, count in sorted(results.items(), key=lambda x: x[1]):
						response = ResponseStat(
										plain_text(text),
										count,
										(count / total) * 100 if total else 0)
						responses.append(response)
				elif IQNonGradableModeledContentPart.providedBy(part):
					kind = 4
					count = 0
					responses = []
					for text in results:
						if not text:
							continue
						text = plain_text(' '.join(text))
						response = ResponseStat(text, count, 0)
						responses.append(response)

				if responses:
					poll_stat.parts.append(
								PollPartStat(kind=kind,
											 content=plain_text(part.content),
											 responses=responses))
			poll_stat_map[poll.ntiid] = poll_stat

		# Now in our order.
		for poll in self.context.questions:
			poll_stat = poll_stat_map.get( poll.ntiid )
			poll_stats.append( poll_stat )

	def _get_displayable(self, source):
		if isinstance(source, string_types):
			source = plain_text(source)
		return source

	def _build_summary(self, options):
		submissions = inquiry_submissions( self.context, self.course )
		creators = _TopCreators( self )
		for submission in submissions or ():
			creators.incr_username( submission.creator.username )

		options['count_for_credit'] = self.count_credit_students
		options['count_open'] = self.count_non_credit_students
		options['count_total'] = self.count_all_students
		options['submit_total'] = creators.total
		options['for_credit_submit_total'] = creators.for_credit_total
		options['non_credit_submit_total'] = creators.non_credit_total
		options['for_credit_submit_perc'] = creators.for_credit_percent_contributed_str
		options['non_credit_submit_perc'] = creators.non_credit_percent_contributed_str

	def __call__(self):
		self._check_access()
		options = self.options
		options['title'] = self.context.title
		self._build_question_data(options)
		self._build_summary(options)
		return options

@view_config(context=IQPoll,
			 name=VIEW_INQUIRY_REPORT)
class PollReportPDF(InquiryReportPDF):

	@Lazy
	def report_title(self):
		return _('Poll Report')

	def _aggregated_polls(self, aggregated):
		if aggregated:
			yield aggregated

@view_config(context=IQSurvey,
			 name=VIEW_INQUIRY_REPORT)
class SurveyReportPDF(InquiryReportPDF):

	@Lazy
	def report_title(self):
		return _('Survey Report')

	def _aggregated_polls(self, aggregated):
		for agg_poll in aggregated:
			yield agg_poll

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from pyramid.view import view_config

from nti.app.products.courseware.interfaces import IVideoUsageStats

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports import VIEW_VIDEO_REPORT

from nti.app.products.courseware_reports.views.view_mixins import AbstractCourseReportView

from nti.contenttypes.courses.interfaces import ICourseInstance

logger = __import__('logging').getLogger(__name__)


@view_config(context=ICourseInstance,
			 name=VIEW_VIDEO_REPORT)
class VideoUsageReportPdf(AbstractCourseReportView):

	report_title = _(u'Video Usage Report')

	def __call__(self):
		self._check_access()
		options = self.options
		video_usage = IVideoUsageStats(self.context, None)
		if video_usage is not None:
			options['top_video_usage'] = video_usage.get_top_stats()
			options['all_video_usage'] = video_usage.get_stats()
		return options

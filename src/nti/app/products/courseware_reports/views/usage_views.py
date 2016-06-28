#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from pyramid.view import view_config

from nti.app.products.courseware.interfaces import IVideoUsageStats

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports import VIEW_VIDEO_REPORT

from nti.app.products.courseware_reports.views.view_mixins import _AbstractReportView

from nti.contenttypes.courses.interfaces import ICourseInstance

@view_config(context=ICourseInstance,
			 name=VIEW_VIDEO_REPORT)
class VideoUsageReportPdf(_AbstractReportView):

	report_title = _('Video Usage Report')

	def __call__(self):
		self._check_access()
		options = self.options
		video_usage = IVideoUsageStats(self.context, None)
		if video_usage is not None:
			options['top_video_usage'] = video_usage.get_top_stats()
			options['all_video_usage'] = video_usage.get_stats()
		return options

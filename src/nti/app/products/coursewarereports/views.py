#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
$Id$
"""
from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import component

from itertools import groupby

import BTrees
from pyramid.view import view_config
from pyramid.traversal import find_interface

from zope.catalog.interfaces import ICatalog
from zope.catalog.catalog import ResultSet

from zope.intid.interfaces import IIntIds

from nti.app.assessment.interfaces import ICourseAssignmentCatalog
from nti.app.assessment.interfaces import IUsersCourseAssignmentHistory
from nti.app.assessment.interfaces import get_course_assignment_predicate_for_user
from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment
from nti.app.products.gradebook.interfaces import IGrade
from nti.dataserver.interfaces import IUser
from nti.dataserver.contenttypes.forums.interfaces import ICommunityBoard

from nti.dataserver.metadata_index import CATALOG_NAME
from nti.zope_catalog.datetime import TimestampNormalizer

from nti.app.base.abstract_views import AbstractAuthenticatedView

from .interfaces import ACT_VIEW_REPORTS

@view_config(route_name='objects.generic.traversal',
			 context=ICourseInstanceEnrollment,
			 request_method='GET',
			 permission=ACT_VIEW_REPORTS,
			 name='StudentParticipationReport.pdf',
			 renderer="templates/StudentParticipationReport.rml")
class StudentParticipationReportPdf(AbstractAuthenticatedView):

	FORUM_OBJECT_MIMETYPES = ['application/vnd.nextthought.forums.generalforumcomment',
							  'application/vnd.nextthought.forums.communityforumcomment',
							  'application/vnd.nextthought.forums.communitytopic']

	def __call_(self):
		md_catalog = component.getUtility(ICatalog, CATALOG_NAME)
		uidutil = component.getUtility(IIntIds)
		course = self.context.CourseInstance
		student_user = IUser(self.context)
		course_board = course.Discussions
		# Collect data and return it in a form to be rendered
		# (a dictionary containing data and callable objects)

		# Graph of forum participation over time (time-series of forum-related
		# objects created bucketed by something--day/week?) probably a linePlot?
		# We find these objects using the catalog rather than traversing through
		# all possible forums/topics of the course on the theory that the total
		# number of objects the user created is going to be smaller than
		# all the objects in the course discussion board. This could be further improved
		# by applying a time limit to the objects the user created.
		intids_created_by_student = md_catalog['creator'].apply({'all_of': (self.context.Username,)})
		intids_of_forum_objects = md_catalog['mimeType'].apply({'any_of': self.FORUM_OBJECT_MIMETYPES})
		# We could apply based on createdTime to be no less than the start time of the
		# course
		intids_of_forum_objects_created_by_student = md_catalog.family.IF.intersection(intids_created_by_student, intids_of_forum_objects)
		forum_objects_created_by_student = ResultSet(intids_of_forum_objects_created_by_student,
													 uidutil )
		forum_objects_created_by_student_in_course = [x for x in forum_objects_created_by_student
													  if find_interface(x, ICommunityBoard) == course_board]
		# Group the forum objects by day
		day_normalizer = TimestampNormalizer(TimestampNormalizer.RES_DAY)
		day_key = lambda x: day_normalizer.value(x.createdTime)
		forum_objects_created_by_student_in_course.sort(key=day_key)

		forum_objects_by_day = BTrees.family64.II.BTree()
		for k, g in groupby(forum_objects_created_by_student_in_course, day_key):
			forum_objects_by_day[k] = len(list(g))

		# Tabular breakdown of what topics the user created in what forum
		# and how many comments in which topics (could be bulkData or actual blockTable)

		# Each self-assessment and how many times taken (again bulkData)

		# Table of assignment history and grades for all assignments in course

		assignment_catalog = ICourseAssignmentCatalog(course)

		# TODO: Do we need to filter this?
		uber_filter = get_course_assignment_predicate_for_user(student_user, course)
		histories = IUsersCourseAssignmentHistory(course, student_user)
		return {}

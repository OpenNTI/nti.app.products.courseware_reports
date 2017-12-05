#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from pyramid.view import view_config

from zope import component
from zope import interface

from zope.cachedescriptors.property import Lazy

from nti.traversal.traversal import find_interface

from datetime import datetime

from nti.dataserver.interfaces import IUser
from nti.dataserver.users.users import User

from nti.app.products.courseware_reports import MessageFactory as _
from nti.app.products.courseware_reports import VIEW_USER_ENROLLMENT
from nti.contenttypes.courses.utils import get_context_enrollment_records
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.app.products.courseware_reports.interfaces import IPDFReportView
from nti.app.products.courseware_reports.interfaces import IPDFReportHeaderManager
from nti.app.products.courseware_reports.reports import StudentInfo
from nti.app.products.courseware_reports.reports import _adjust_date
from nti.app.products.courseware_reports.reports import _format_datetime
from nti.app.products.courseware_reports.views.view_mixins import _AbstractReportView
from nti.dataserver.authorization import ACT_READ

@view_config(context=IUser,
             name=VIEW_USER_ENROLLMENT)

class UserEnrollmentReportPdf(_AbstractReportView):
  report_title = _('User Enrollment Report')

  def get_context_enrollment_records(self):
    return get_context_enrollment_records(self.context, self.remoteUser)

  def get_course_for_node(self, node):
    return find_interface(node, ICourseInstance, strict=False)

  def build_user_info(self, user):
    return StudentInfo(user)

  def get_user_info(self):
    return self.build_user_info(self.context)

  def generate_footer(self):
    date = _adjust_date(datetime.utcnow())
    date = date.strftime('%b %d, %Y %I:%M %p')
    title = self.report_title
    user = self.context.username
    return "%s %s %s" % (title, user, date)

  def __init__(self, context, request):
    self.context = context
    self.request = request
    self.remoteUser = User.get_user(request.remote_user)
    self.options = {}

    if request.view_name:
      self.filename = request.view_name

  def __call__(self):
    options = self.options
    records = self.get_context_enrollment_records()
    records = sorted(records, key=lambda x:x.createdTime, reverse=True)

    options["user"] = self.get_user_info()

    options["enrollments"] = []
    
    for record in records:
      enrollment = {}
      
      course = self.get_course_for_node(record)
      course = ICourseCatalogEntry(course)
      
      enrollment["title"] = course.title
      
      if record.createdTime:
        time = datetime.fromtimestamp(record.createdTime)
        enrollment["createdTime"] = _format_datetime(_adjust_date(time))
      
      options["enrollments"].append(enrollment)

    return options
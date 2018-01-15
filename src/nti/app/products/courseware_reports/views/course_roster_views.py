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

from pyramid.httpexceptions import HTTPForbidden

from zope.cachedescriptors.property import Lazy

from datetime import datetime

from nti.dataserver.interfaces import IUser

from nti.app.products.courseware_reports import MessageFactory as _
from nti.app.products.courseware_reports import VIEW_COURSE_ROSTER
from nti.app.products.courseware_reports.reports import _adjust_date
from nti.app.products.courseware_reports.reports import _format_datetime
from nti.app.products.courseware_reports.views.view_mixins import AbstractCourseReportView
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.dataserver.authorization import is_admin_or_site_admin
from nti.contenttypes.courses.interfaces import ICourseEnrollments

@view_config(context=ICourseInstance,
             name=VIEW_COURSE_ROSTER)

class CourseRosterReportPdf(AbstractCourseReportView):
  report_title = _('Course Roster Report')

  def _check_access(self):
    if is_admin_or_site_admin(self.remoteUser):
      return True

    raise HTTPForbidden()

  def __init__(self, context, request):
    self.context = context
    self.request = request

    if 'remoteUser' in request.params:
      self.remoteUser = request.params['remoteUser']
    else:
      self.remoteUser = self.getRemoteUser()
        
    self.options = {}

    if request.view_name:
      self.filename = request.view_name

  def __call__(self):
    
    self._check_access()
    options = self.options
    
    course = self.course
    
    enrollmentCourses = ICourseEnrollments(course)

    enrollments = []
    for record in enrollmentCourses.iter_enrollments():
      enrollRecord = {}
      
      enrollRecord["username"] = IUser(record).username
      
      if record.createdTime:
        time = datetime.fromtimestamp(record.createdTime)
        enrollRecord["enrollmentTime"] = _format_datetime(_adjust_date(time))
        enrollRecord["lastAccessed"] = ""
          
      enrollments.append(enrollRecord)

    options["enrollments"] = enrollments
    options["TotalEnrolledCount"] = enrollmentCourses.count_enrollments()
    

    return options
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
from nti.dataserver.interfaces import ISiteAdminUtility
from nti.dataserver.users.users import User

from nti.app.products.courseware_reports import MessageFactory as _
from nti.app.products.courseware_reports import VIEW_USER_ENROLLMENT
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry
from nti.app.products.courseware_reports.reports import _adjust_date
from nti.app.products.courseware_reports.reports import _format_datetime
from nti.app.products.courseware_reports.views.view_mixins import AbstractReportView
from nti.contenttypes.courses.utils import get_context_enrollment_records
from nti.traversal.traversal import find_interface
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.dataserver.authorization import is_site_admin
from nti.dataserver.authorization import is_admin


@view_config(context=IUser,
             name=VIEW_USER_ENROLLMENT)

class UserEnrollmentReportPdf(AbstractReportView):
  report_title = _('User Enrollment Report')

  def _check_access(self):
    if is_admin(self.remoteUser) or self.context == self.remoteUser:
      return True
    
    if is_site_admin(self.remoteUser):
      admin_utility = component.getUtility(ISiteAdminUtility)
      if admin_utility.can_administer_user(self.remoteUser, self.context):
        return True
      
    raise HTTPForbidden()

  def get_user_info(self):
      return self.build_user_info(self.context)

  def generate_footer(self):
    date = _adjust_date(datetime.utcnow())
    date = date.strftime('%b %d, %Y %I:%M %p')
    title = self.report_title
    user = self.context.username
    return "%s %s %s" % (title, user, date)

  def get_context_enrollment_records(self):
    return get_context_enrollment_records(self.context, self.remoteUser)

  def __init__(self, context, request):
    self.context = context
    self.request = request

    self.remoteUser = self.getRemoteUser()
    self.options = {}

    if request.view_name:
      self.filename = request.view_name

  def __call__(self):
    self._check_access()
    options = self.options
    records = self.get_context_enrollment_records()
    records = sorted(records, key=lambda x:x.createdTime)

    options["user"] = self.get_user_info()

    options["enrollments"] = []
    for record in records:
      enrollment = {}
      
      course = ICourseCatalogEntry(ICourseInstance(record))
      
      enrollment["title"] = course.title
      
      if record.createdTime:
        time = datetime.fromtimestamp(record.createdTime)
        enrollment["createdTime"] = _format_datetime(_adjust_date(time))
      
      options["enrollments"].append(enrollment)

    return options
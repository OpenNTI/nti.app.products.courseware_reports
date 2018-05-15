#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from zope import interface
from zope import component

from nti.contenttypes.reports.interfaces import IReportAvailablePredicate

from nti.dataserver.authorization import is_site_admin
from nti.dataserver.authorization import is_admin

from nti.dataserver.interfaces import ISiteAdminUtility

from nti.externalization.interfaces import StandardExternalFields

LINKS = StandardExternalFields.LINKS

logger = __import__('logging').getLogger(__name__)


@interface.implementer(IReportAvailablePredicate)
class UserTranscriptPredicate(object):

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, unused_report, context, user):
        result = False
        if is_admin(user) or context == user:
            result = True
        elif is_site_admin(user):
            admin_utility = component.getUtility(ISiteAdminUtility)
            result = admin_utility.can_administer_user(user, context)
        return result

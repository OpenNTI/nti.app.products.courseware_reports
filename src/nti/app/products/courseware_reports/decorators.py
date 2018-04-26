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

from zope.cachedescriptors.property import Lazy

from zope.location.interfaces import ILocation

from nti.app.assessment.common.submissions import has_submissions

from nti.app.contenttypes.reports.reports import DefaultReportLinkProvider

from nti.app.products.courseware.interfaces import ICoursesWorkspace

from nti.app.products.courseware_reports import VIEW_ALL_COURSE_ROSTER

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports.utils import find_course_for_user

from nti.app.products.gradebook.interfaces import IGradeBook

from nti.app.renderers.decorators import AbstractAuthenticatedRequestAwareDecorator

from nti.assessment.interfaces import IQInquiry

from nti.contenttypes.courses.interfaces import ICourseCatalog
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import IGlobalCourseCatalog

from nti.contenttypes.courses.utils import get_course_enrollments

from nti.contenttypes.reports.interfaces import IReportAvailablePredicate

from nti.dataserver.authorization import is_admin_or_site_admin

from nti.links.links import Link

from nti.traversal.traversal import find_interface

from nti.dataserver.authorization import is_site_admin
from nti.dataserver.authorization import is_admin

from nti.dataserver.interfaces import ISiteAdminUtility

from nti.externalization.interfaces import StandardExternalFields
from nti.externalization.interfaces import IExternalObjectDecorator

LINKS = StandardExternalFields.LINKS

logger = __import__('logging').getLogger(__name__)


class AbstractFromCourseEvaluator(object):
    """
    Defines a class that involves knowing about a course
    """

    def __init__(self, *args, **kwargs):
        pass

    def _course_from_context(self, context, user):
        self.course = find_interface(context, ICourseInstance, strict=False)
        if self.course is None:
            self.course = find_course_for_user(context, user)
        return self.course


"""
Predicates the evaluate if that kind of report
should be decorated onto the corresponding context
for that user.
"""


@interface.implementer(IReportAvailablePredicate)
class AbstractFromCoursePredicate(AbstractFromCourseEvaluator):

    def evaluate(self, unused_report, unused_context, unused_user):
        return True


@interface.implementer(IReportAvailablePredicate)
class ForumParticipationPredicate():

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, unused_report, context, unused_user):
        return (bool(context) and any(bool(x.values()) for x in context.values()))


@interface.implementer(IReportAvailablePredicate)
class TopicParticipationPredicate():

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, unused_report, context, unused_user):
        return bool(context.values())


class CourseInstancePredicate(AbstractFromCoursePredicate):

    def evaluate(self, unused_report, context, user):
        course = self._course_from_context(context, user)
        return course is not None and get_course_enrollments(course) is not None


class AssignmentPredicate(AbstractFromCoursePredicate):

    def evaluate(self, unused_report, context, user):
        course = self._course_from_context(context, user)
        book = IGradeBook(course, None)
        if book is not None:
            entry = book.getColumnForAssignmentId(context.__name__)
            result = entry is not None and bool(entry.items())
            return result
        return False


class InquiryPredicate(AbstractFromCoursePredicate):

    def evaluate(self, unused_report, context, user):
        course = self._course_from_context(IQInquiry(context, None), user)
        if course is not None and has_submissions(context, course):
            self.inquiry = IQInquiry(context, None)
            return self.inquiry is not None
        return False

@interface.implementer(IReportAvailablePredicate)
class UserEnrollmentPredicate(object):

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


"""
Link providers that, given a context, will define the proper link
elements to be decorated onto the context
"""


class AbstractFromCourseLinkProvider(DefaultReportLinkProvider,
                                     AbstractFromCourseEvaluator):
    """
    Defines a link provider that comes from a course context
    """


class AssignmentSummaryLinkProvider(AbstractFromCourseLinkProvider):

    def link(self, report, context, user):
        course = self._course_from_context(context, user)
        book = IGradeBook(course, None)
        if book is not None:
            entry = book.getColumnForAssignmentId(context.__name__)
            if entry is not None:
                return Link(entry,
                            rel="report-%s" % report.name,
                            elements=("@@" + report.name,),
                            title=_(report.title))
        return None


class InquiryLinkProvider(AbstractFromCourseLinkProvider):

    def link(self, report, context, user):
        course = self._course_from_context(IQInquiry(context, None), user)
        rel = "report-%s" % report.name
        report_element = "@@" + report.name
        elements = (report_element,)
        if course is not None:
            elements = ('Assessments', context.ntiid, report_element)
            context = course
        return Link(context,
                    rel=rel,
                    elements=elements,
                    title=_(report.title))


@component.adapter(ICoursesWorkspace)
@interface.implementer(IExternalObjectDecorator)
class _CourseWorkspaceReportDecorator(AbstractAuthenticatedRequestAwareDecorator):
    """
    A decorator that provides the all course roster link on the catalog.
    Ideally, this would be decorated automatically as some `global` report,
    for contexts that do not get externalized.
    """

    @Lazy
    def catalog(self):
        return component.queryUtility(ICourseCatalog)

    def _predicate(self, unused_context, unused_result):
        return self.catalog is not None \
           and not IGlobalCourseCatalog.providedBy(self.catalog) \
           and is_admin_or_site_admin(self.remoteUser)

    def _do_decorate_external(self, context, result):
        _links = result.setdefault(LINKS, [])
        link = Link(self.catalog,
                    rel=VIEW_ALL_COURSE_ROSTER,
                    elements=('@@%s' % VIEW_ALL_COURSE_ROSTER,))
        interface.alsoProvides(link, ILocation)
        link.__name__ = ''
        link.__parent__ = context
        _links.append(link)

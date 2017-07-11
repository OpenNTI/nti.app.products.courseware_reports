#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from zope import interface

from nti.app.assessment.common import has_submissions

from nti.app.contenttypes.reports.reports import DefaultReportLinkProvider

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports.utils import find_course_for_user

from nti.app.products.gradebook.interfaces import IGradeBook

from nti.assessment.interfaces import IQInquiry

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.contenttypes.courses.utils import get_course_enrollments

from nti.contenttypes.reports.interfaces import IReportAvailablePredicate

from nti.links.links import Link

from nti.traversal.traversal import find_interface


class AbstractFromCourseEvaluator():
    """
    Defines a class that involves knowing
    about a course
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

    def evaluate(self, report, context, user):
        return True


@interface.implementer(IReportAvailablePredicate)
class ForumParticipationPredicate():

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, report, context, user):
        return (bool(context) and any(bool(x.values()) for x in context.values()))


@interface.implementer(IReportAvailablePredicate)
class TopicParticipationPredicate():

    def __init__(self, *args, **kwargs):
        pass

    def evaluate(self, report, context, user):
        return bool(context.values())


class CourseInstancePredicate(AbstractFromCoursePredicate):

    def evaluate(self, report, context, user):
        course = self._course_from_context(context, user)
        return get_course_enrollments(course) is not None


class AssignmentPredicate(AbstractFromCoursePredicate):

    def evaluate(self, report, context, user):
        course = self._course_from_context(context, user)
        book = IGradeBook(course)
        entry = book.getColumnForAssignmentId(context.__name__)
        result = entry is not None and bool(entry.items())
        return result


class InquiryPredicate(AbstractFromCoursePredicate):

    def evaluate(self, report, context, user):
        course = self._course_from_context(IQInquiry(context, None), user)
        if has_submissions(context, course):
            self.inquiry = IQInquiry(context, None)
            return self.inquiry is not None
        return False


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

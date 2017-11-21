#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
__docformat__ = "restructuredtext en"

from pyramid.threadlocal import get_current_request

from zope import component

from nti.contentlibrary.interfaces import IContentPackage

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseAdministrativeLevel

from nti.traversal.traversal import find_interface

logger = __import__('logging').getLogger(__name__)


def course_from_forum(forum):
    # If we are directly enclosed inside a course
    # (as we should be for non-legacy,) that's what
    # we want
    course = find_interface(forum, ICourseInstance)
    if course is not None:
        return course

    # otherwise, in the legacy case, we need to tweak
    # the community to get where we want to go
    board = forum.__parent__
    community = board.__parent__
    courses = ICourseAdministrativeLevel(community, None)
    if courses:
        # Assuming only one
        course = list(courses.values())[0]
        assert course.Discussions == board
        return course


def get_course_from_request(request=None):
    request = get_current_request() if request is None else request
    course = ICourseInstance(request, None)
    return course


def find_course_for_user(data, user, request=None):
    # Prefer course from request if we have it.
    course = get_course_from_request(request)
    if course is not None:
        return course

    course = ICourseInstance(data, None)
    if course is not None:
        return course

    if user is not None:
        # Try to find the course within the context of the user;
        # this takes into account the user's enrollment status
        # to find the best course (sub) instance
        course = component.queryMultiAdapter((data, user),
                                             ICourseInstance)

    if course is None:
        # Ok, can we get there generically, via course package
        # This can be very expensive.
        package = find_interface(data, IContentPackage, strict=False)
        course = ICourseInstance(package, None)
        if course is not None:
            # Snap. Well, we found a course (good!), but not by taking
            # the user into account (bad!)
            logger.debug("No enrollment for user %s in course %s found "
                         "for data %s; assuming generic/global course instance",
                         user, course, data)

    return course

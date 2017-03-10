#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from pyramid.threadlocal import get_current_request

from zope import component

from nti.contentlibrary.interfaces import IContentPackage

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry
from nti.contenttypes.courses.interfaces import ICourseAdministrativeLevel

from nti.traversal.traversal import find_interface


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

    if user is None:
        return None

    if ICourseCatalogEntry.providedBy(data):
        data = ICourseInstance(data)

    if ICourseInstance.providedBy(data):
        # Yay, they gave us one directly!
        course = data
    else:
        # Try to find the course within the context of the user;
        # this takes into account the user's enrollment status
        # to find the best course (sub) instance
        course = component.queryMultiAdapter((data, user), ICourseInstance)

    if course is None:
        # Ok, can we get there genericlly, as in the old-school
        # fashion?
        course = ICourseInstance(data, None)
        if course is None:
            # Hmm, maybe we have an assignment-like object and we can
            # try to find the content package it came from and from there
            # go to the one-to-one mapping to courses we used to have
            course = ICourseInstance(find_interface(data, IContentPackage, strict=False),
                                     None)
        if course is not None:
            # Snap. Well, we found a course (good!), but not by taking
            # the user into account (bad!)
            logger.debug("No enrollment for user %s in course %s found "
                         "for data %s; assuming generic/global course instance",
                         user, course, data)

    return course
_find_course_for_user = find_course_for_user

VIDEO_COMPLETION_THRESHOLD = 0.9


def _check_video_completion(video):
    total_duration = _video_duration_to_seconds(video.video_duration)
    watched_duration = _video_duration_to_seconds(
        video.watch_times.average_total_watch_time)

    if float(watched_duration) / total_duration >= VIDEO_COMPLETION_THRESHOLD:
        return True
    return False


def _video_duration_to_seconds(str_duration):
    duration = [int(i) for i in str_duration.split(':')]
    seconds = duration[-1]
    seconds += duration[-2] * 60
    return seconds

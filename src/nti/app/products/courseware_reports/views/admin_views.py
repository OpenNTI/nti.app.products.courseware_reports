#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import csv
import time
from io import BytesIO
from numbers import Number

from six import string_types
from six.moves import urllib_parse

from pyramid.view import view_config

from zope import component

from zope.cachedescriptors.property import Lazy
from zope.cachedescriptors.property import CachedProperty

from zope.intid.interfaces import IIntIds

from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.app.assessment.common.evaluations import get_course_assignments
from nti.app.assessment.common.evaluations import get_course_self_assessments

from nti.app.assessment.interfaces import IUsersCourseAssignmentHistory
from nti.app.assessment.interfaces import IUsersCourseAssignmentHistoryItem

from nti.app.products.courseware.interfaces import IVideoUsageStats
from nti.app.products.courseware.interfaces import ICourseInstanceEnrollment

from nti.app.products.courseware.workspaces import CourseInstanceEnrollment

from nti.app.products.courseware_reports.reports import _do_get_containers_in_course
from nti.app.products.courseware_reports.reports import _get_self_assessments_for_course

from nti.app.products.courseware_reports.views import parse_datetime

from nti.app.products.courseware_reports.views.participation_views import StudentParticipationReportPdf

from nti.app.products.gradebook.interfaces import NO_SUBMIT_PART_NAME

from nti.app.products.gradebook.interfaces import IGrade
from nti.app.products.gradebook.interfaces import IGradeBook

from nti.appserver.account_recovery_views import find_users_with_email

from nti.contentlibrary.indexed_data import get_catalog

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalog
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.contenttypes.courses.interfaces import ICourseAssignmentCatalog

from nti.contenttypes.presentation import RELATED_WORK

from nti.contenttypes.presentation.interfaces import INTIVideo

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import IDataserverFolder
from nti.dataserver.interfaces import IEnumerableEntityContainer

from nti.dataserver.users.users import User

from nti.dataserver.authorization import ACT_MODERATE
from nti.dataserver.authorization import ACT_NTI_ADMIN

from nti.dataserver.metadata.index import CATALOG_NAME

from nti.ntiids.ntiids import is_ntiid_of_type

from nti.site.site import get_component_hierarchy_names

from nti.zope_catalog.catalog import ResultSet

from nti.zope_catalog.interfaces import IDeferredCatalog

logger = __import__('logging').getLogger(__name__)


@view_config(route_name='objects.generic.traversal',
             name='shared_notes',
             renderer='rest',
             request_method='GET',
             context=IDataserverFolder,
             permission=ACT_MODERATE)
def shared_notes(request):
    """
    Return the shared_note count by course.  The shared notes are broken down
    by public, course-only, and private.
    """
    stream = BytesIO()
    writer = csv.writer(stream)
    response = request.response
    response.content_encoding = 'identity'
    response.content_type = 'text/csv; charset=UTF-8'
    response.content_disposition = 'attachment; filename="shared_notes.csv"'

    writer.writerow(['Course', 'Public', 'Course', 'Other (Private)'])

    def all_usernames(course):
        everyone = course.legacy_community
        everyone_usernames = {
            x.lower() for x in IEnumerableEntityContainer(everyone).iter_usernames()
        }
        return everyone_usernames

    course_catalog = component.getUtility(ICourseCatalog)
    md_catalog = component.getUtility(IDeferredCatalog, CATALOG_NAME)
    uidutil = component.getUtility(IIntIds)

    intersection = md_catalog.family.IF.intersection
    intids_of_notes = md_catalog['mimeType'].apply(
        {'any_of': ('application/vnd.nextthought.note',)}
    )

    def _intersect(set1, set2):
        return any(x in set1 for x in set2)

    for course in course_catalog:
        course = ICourseInstance(course)
        course_containers = _do_get_containers_in_course(course)
        intids_of_objects_in_course_containers = \
            md_catalog['containerId'].apply({'any_of': course_containers})

        course_intids_of_notes = intersection(intids_of_notes,
                                              intids_of_objects_in_course_containers)
        notes = ResultSet(course_intids_of_notes, uidutil)

        public_scopes = course.SharingScopes.getAllScopesImpliedbyScope('Public')
        other_scopes = [
            x for x in course.SharingScopes.values() if x not in public_scopes
        ]

        shared_public = 0
        shared_course = 0
        shared_other = 0

        course_users = all_usernames(course)
        notes = (
            x for x in notes if x.creator.username.lower() in course_users
        )

        for note in notes:
            if _intersect(public_scopes, note.sharingTargets):
                shared_public += 1
            elif _intersect(other_scopes, note.sharingTargets):
                shared_course += 1
            else:
                shared_other += 1

        writer.writerow(
            [course.__name__, shared_public, shared_course, shared_other]
        )

    stream.flush()
    stream.seek(0)
    response.body_file = stream
    return response


def _get_self_assessments_for_user(username, intids_of_submitted_qsets,
                                   self_assessment_qsids, self_assessments,
                                   md_catalog, intersection, uidutil):
    # XXX this logic duplicated in .views
    intids_by_student = md_catalog['creator'].apply({'any_of': (username,)})
    intids_of_submitted_qsets_by_student = intersection(intids_of_submitted_qsets,
                                                        intids_by_student)
    qsets_by_student = [x for x in ResultSet(intids_of_submitted_qsets_by_student, uidutil)
                        if x.questionSetId in self_assessment_qsids]

    title_to_count = dict()

    def _title_of_qs(qs):
        if qs.title:
            return qs.title
        return qs.__parent__.title

    for asm in self_assessments:
        title_to_count[_title_of_qs(asm)] = 0
    for submission in qsets_by_student:
        asm = self_assessment_qsids[submission.questionSetId]
        title_to_count[_title_of_qs(asm)] += 1
    return title_to_count


def _get_assignment_count(course, user, assignment_catalog):
    # XXX this logic duplicated in .views
    unique_assignment_count = 0
    histories = component.getMultiAdapter((course, user),
                                          IUsersCourseAssignmentHistory)

    for assignment in assignment_catalog.iter_assignments():
        history_item = histories.get(assignment.ntiid)
        if history_item:
            unique_assignment_count += 1
    return unique_assignment_count


def _get_final_gradebook_entry(course):
    gradebook = IGradeBook(course)
    for part in gradebook.values():
        for name, entry in part.items():
            if part.__name__ == NO_SUBMIT_PART_NAME and name == 'Final Grade':
                return entry


def _get_course(course_name, course_catalog):
    for course_entry in course_catalog:
        if course_entry.__name__ == course_name:
            return ICourseInstance(course_entry)


@view_config(route_name='objects.generic.traversal',
             name='whitelist_participation',
             renderer='rest',
             request_method='POST',
             context=IDataserverFolder,
             permission=ACT_MODERATE)
def whitelist_participation(request):
    """
    Return the participation of students found in a whitelist.
    """
    stream = BytesIO()
    writer = csv.writer(stream)
    response = request.response
    response.content_encoding = 'identity'
    response.content_type = 'text/csv; charset=UTF-8'
    response.content_disposition = 'attachment; filename="whitelist_participation.csv"'

    # Inputs
    # -CSV of email addresses
    # -Course
    values = urllib_parse.unquote(request.body)
    user_emails = set(values.split())
    course_name = request.headers.get('NTcourse')

    course_catalog = component.getUtility(ICourseCatalog)
    md_catalog = component.getUtility(IDeferredCatalog, CATALOG_NAME)
    uidutil = component.getUtility(IIntIds)
    intersection = md_catalog.family.IF.intersection

    course = _get_course(course_name, course_catalog)

    # SelfAssessments
    self_assessments = _get_self_assessments_for_course(course)
    course_self_assessment_count = len(self_assessments)
    self_assessment_qsids = {x.ntiid: x for x in self_assessments}
    intids_of_submitted_qsets = md_catalog['mimeType'].apply(
        {'any_of': ('application/vnd.nextthought.assessment.assessedquestionset',)}
    )

    # Assignments
    assignment_catalog = ICourseAssignmentCatalog(course)
    course_assignment_count = len(
        [x for x in assignment_catalog.iter_assignments()])

    # FinalGrades
    final_grade_entry = _get_final_gradebook_entry(course)

    self_assessment_header = 'Self-Assessments Completed (%s)' % course_self_assessment_count
    assignment_header = 'Assignments Completed (%s)' % course_assignment_count
    writer.writerow(
        ['Email', self_assessment_header,
         assignment_header, 'Has Final Grade', 'Final Grade']
    )

    for email in user_emails:
        users = find_users_with_email(email, dataserver=None)
        if not users:
            writer.writerow([email + '(NOT FOUND)', 'N/A', 'N/A', 'No', 'N/A'])
            continue

        if len(users) > 1:
            # We could capture all or only capture the first or skip or combine
            # results
            pass

        user = users[0]
        username = user.username.lower()

        # Self-Assessments
        title_to_count = _get_self_assessments_for_user(username,
                                                        intids_of_submitted_qsets,
                                                        self_assessment_qsids,
                                                        self_assessments, md_catalog, intersection,
                                                        uidutil)

        unique_self_assessment_count = sum(
            [1 for x in title_to_count.values() if x])

        # Assignments
        unique_assignment_count = _get_assignment_count(
            course, user, assignment_catalog)

        # Final grade
        if final_grade_entry.has_key(username):
            has_final_grade = u'Yes'
            final_grade_val = final_grade_entry[username].value
        else:
            has_final_grade = u'No'
            final_grade_val = u'-'

        writer.writerow([email, unique_self_assessment_count,
                         unique_assignment_count, has_final_grade, final_grade_val])

    stream.flush()
    stream.seek(0)
    response.body_file = stream
    return response


class InstructorParticipationReport(StudentParticipationReportPdf):
    """
    Collects information that may be useful to analyze instructor
    participation in a course.
    """

    @CachedProperty
    def _containers_in_course(self):
        containers_in_course = _do_get_containers_in_course(self.course)
        return self.md_catalog['containerId'].apply({'any_of': containers_in_course})

    def _get_feedback_count(self):
        # Really expensive
        gradebook = IGradeBook(self.course)
        assignment_catalog = get_course_assignments(self.course)
        feedback_count = 0

        for asg in assignment_catalog:
            column = gradebook.getColumnForAssignmentId(asg.ntiid)
            for grade in column.values():
                try:
                    history = IUsersCourseAssignmentHistoryItem(grade)
                except TypeError:  # Deleted user
                    continue

                for feedback in history.Feedback.values():
                    if feedback.creator == self.student_user:
                        feedback_count += 1

        return feedback_count

    def _get_note_count(self):
        md_catalog = self.md_catalog
        intersection = md_catalog.family.IF.intersection

        intids_of_notes = md_catalog['mimeType'].apply(
            {'any_of': ('application/vnd.nextthought.note',)}
        )
        intids_of_objects_in_course_containers = self._containers_in_course

        intids_of_notes = intersection(intids_of_notes,
                                       intids_of_objects_in_course_containers)

        intids_of_instructor = self.intids_created_by_student
        intids_of_notes = intersection(intids_of_notes, intids_of_instructor)
        return len(intids_of_notes)

    def __call__(self):
        options = self.options
        self._build_user_info(options)
        self._build_forum_data(options)
        options['NoteCount'] = self._get_note_count()
        options['AssignmentFeedbackCount'] = self._get_feedback_count()
        return options


@view_config(route_name='objects.generic.traversal',
             name='InstructorParticipation',
             renderer='rest',
             request_method='GET',
             context=IDataserverFolder,
             permission=ACT_NTI_ADMIN)
class InstructorParticipationView(AbstractAuthenticatedView):
    """
    Iterates the catalog and produces instructor participation
    stats for each instructor in each course.  Optionally filtered
    by username or by course start date.
    """

    def __call__(self):
        values = self.request.params
        start_time = parse_datetime(values.get('start_time'))
        usernames = values.get('usernames') or u''
        usernames = set(User.get_user(x) for x in usernames.split())
        catalog = component.getUtility(ICourseCatalog)

        response = self.request.response
        response.content_encoding = 'identity'
        response.content_type = 'text/csv; charset=UTF-8'
        response.content_disposition = 'attachment; filename="instructor_participation.csv"'

        stream = BytesIO()
        writer = csv.writer(stream)

        # We do not bother with super-course instance collecting
        # at the subinstance level. We should have the public instance
        # in our iteration and we do not want to double-count.
        header = [
            'Display Name', 'Username', 'Course', 'Topics Created',
            'Comments Created', 'Notes Created', 'Assignment Feedback Created'
        ]
        writer.writerow(header)

        for catalog_entry in catalog.iterCatalogEntries():
            # Filter by start date
            if      start_time \
                and catalog_entry.StartDate \
                and start_time > time.mktime(catalog_entry.StartDate.timetuple()):
                continue

            # Filter by usernames param
            course = ICourseInstance(catalog_entry)
            instructors = set(course.instructors)
            to_check = usernames.intersection(instructors) if usernames else instructors

            for instructor in to_check:
                instructor = IUser(instructor, None)
                if instructor is None:
                    continue
                enrollment = component.queryMultiAdapter((course, instructor),
                                                         ICourseInstanceEnrollment)
                if enrollment is None:
                    # Force it
                    enrollment = CourseInstanceEnrollment(course, instructor)

                spr = InstructorParticipationReport(enrollment, self.request)

                options = spr()
                user_info = options['user']
                comments_created = options['total_forum_objects_created']
                topics_created = len(options['topics_created'])
                note_count = options['NoteCount']
                feedback_count = options['AssignmentFeedbackCount']
                writer.writerow((user_info.display, user_info.username,
                                 catalog_entry.ProviderUniqueID,
                                 topics_created, comments_created,
                                 note_count, feedback_count))
        stream.flush()
        stream.seek(0)
        response.body_file = stream
        return response


def _tx_string(s):
    if s is not None and isinstance(s, unicode):
        s = s.encode('utf-8')
    return s


def _write(data, writer, stream):
    writer.writerow([_tx_string(x) for x in data])
    return stream


@view_config(route_name='objects.generic.traversal',
             name='StudentParticipationCSV',
             renderer='rest',
             request_method='GET',
             context=ICourseInstance,
             permission=ACT_NTI_ADMIN)
class StudentParticipationCSVView(AbstractAuthenticatedView):
    """
    Given a CSV of student usernames, return a CSV of
    participation statistics for those students. Expects
    a CSV with a header and a column named `username`.
    """

    @Lazy
    def student_user(self):
        return IUser(self.context)

    @Lazy
    def course(self):
        return ICourseInstance(self.context)

    def get_qset_submissions(self, usernames):
        usernames = {x.lower() for x in usernames}
        md_catalog = component.getUtility(IDeferredCatalog, CATALOG_NAME)
        uidutil = component.getUtility(IIntIds)
        intids_created = md_catalog['creator'].apply({'any_of': usernames})
        self_assessments = get_course_self_assessments(self.course)
        self_assessment_qsids = {x.ntiid: x for x in self_assessments}

        intids_of_submitted_qsets = md_catalog['mimeType'].apply(
            {'any_of': ('application/vnd.nextthought.assessment.assessedquestionset',)}
        )
        intids_of_submitted_qsets_by_student = md_catalog.family.IF.intersection(intids_of_submitted_qsets,
                                                                                 intids_created)

        qsets_by_student_in_course = [
            x for x in ResultSet(intids_of_submitted_qsets_by_student, uidutil)
            if x.questionSetId in self_assessment_qsids
        ]

        return qsets_by_student_in_course

    def _get_users_from_request(self, request):

        reader = csv.DictReader(request.body_file)
        return set((User.get_user(x['username']) for x in reader))

    def _get_all_videos(self):

        catalog = get_catalog()
        rs = catalog.search_objects(container_ntiids=(ICourseCatalogEntry(self.context).ntiid,),
                                    sites=get_component_hierarchy_names(),
                                    provided=INTIVideo)
        videos = [x for x in rs]
        return sorted(videos, key=lambda x: x.title)

    def __call__(self):

        users = self._get_users_from_request(self.request)

        response = self.request.response
        response.content_encoding = 'identity'
        response.content_type = 'text/csv; charset=UTF-8'
        response.content_disposition = 'attachment; filename="student_participation.csv"'

        stream = BytesIO()
        writer = csv.writer(stream)

        videos = self._get_all_videos()

        user_self_assess = dict()
        assignment_catalog = get_course_assignments(self.course)
        assessments = get_course_self_assessments(self.course)
        qset_submissions = self.get_qset_submissions([x.username for x in users])
        for submission in qset_submissions or ():
            if submission.creator.username not in user_self_assess:
                user_self_assess[submission.creator.username] = dict()
            user_tmp = user_self_assess[submission.creator.username]
            if submission.questionSetId not in user_tmp:
                user_tmp[submission.questionSetId] = 0
            user_tmp[submission.questionSetId] += 1

        # construct a header row with the names of all the columns we'll need.
        # TODO: Add stats for readings
        header_row = ['username']
        for video in videos:
            header_row.append('[VideoCompleted] ' + video.title)
            header_row.append('[VideoViewCount] ' + video.title)
        for assignment in assignment_catalog:
            header_row.append('[AssignmentGrade] ' + (assignment.title or ''))

        for assessment in assessments or ():
            title = assessment.title or getattr(assessment.__parent__, 'title', '')
            header_row.append('[SelfAssessment] ' + title)
        _write(header_row, writer, stream)

        # For each username, generate a row of data. It's very important
        # that the fields in this row match the fields in the header, or
        # else the resulting CSV will be incorrect.
        for user in users:
            row_data = [user.username]
            video_usage_stats = component.queryMultiAdapter((self.course, user),
                                                            IVideoUsageStats)

            viewed_videos = video_usage_stats.get_stats()
            user_video = {x.ntiid: x for x in viewed_videos}

            # Add all the video completion data, in order
            for video in videos:
                video_stat = user_video.get(video.ntiid)
                if video_stat:
                    if video_stat.number_watched_completely >= 1:
                        row_data.append('Completed')
                    else:
                        row_data.append('')
                    row_data.append(video_stat.view_event_count)
                else:
                    # append two rows: one for completion status and one for
                    # view count
                    row_data.append('')
                    row_data.append('')

            histories = component.getMultiAdapter((self.course, user),
                                                  IUsersCourseAssignmentHistory)

            # Add the assignment grades
            for assignment in assignment_catalog:
                grade = self._get_grade_from_assignment(assignment, histories)
                row_data.append(grade)

            user_qset_submissions = user_self_assess.get(user.username) or {}
            for self_assess in assessments:
                val = user_qset_submissions.get(self_assess.ntiid, '')
                row_data.append(val)

            # After we have constructed this row, add it to the CSV
            _write(row_data, writer, stream)

        stream.flush()
        stream.seek(0)
        response.body_file = stream
        return response

    def _get_grade_from_assignment(self, assignment, user_histories):
        history_item = user_histories.get(assignment.ntiid)
        if history_item:
            grade_value = getattr(IGrade(history_item, None), 'value', '')
            # Convert the webapp's "number - letter" scheme to a number, iff
            # the letter scheme is empty
            if      grade_value \
                and isinstance(grade_value, string_types) \
                and grade_value.endswith(' -'):
                try:
                    grade_value = float(grade_value.split()[0])
                except ValueError:
                    pass
            if isinstance(grade_value, Number):
                grade_value = '%0.1f' % grade_value
        else:
            grade_value = ''
        return grade_value

    def _get_non_viewed_objects_from_catalog(self, interface, viewed_object_ntiids):
        catalog = get_catalog()
        rs = catalog.search_objects(container_ntiids=(ICourseCatalogEntry(self.context).ntiid,),
                                    sites=get_component_hierarchy_names(),
                                    provided=interface)
        results = []
        for resource in rs:
            if      not is_ntiid_of_type(resource.ntiid, RELATED_WORK) \
                and resource.ntiid not in viewed_object_ntiids:
                results.append(resource)
        return results

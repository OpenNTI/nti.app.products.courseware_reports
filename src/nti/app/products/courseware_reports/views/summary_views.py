#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from itertools import chain
from collections import namedtuple

from pyramid.view import view_config

from zope.cachedescriptors.property import Lazy

from nti.app.products.courseware.interfaces import IVideoUsageStats
from nti.app.products.courseware.interfaces import IResourceUsageStats

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports import VIEW_COURSE_SUMMARY

from nti.app.products.courseware_reports.reports import _TopCreators
from nti.app.products.courseware_reports.reports import _CommonBuckets
from nti.app.products.courseware_reports.reports import _format_datetime
from nti.app.products.courseware_reports.reports import _adjust_timestamp
from nti.app.products.courseware_reports.reports import _DateCategoryAccum
from nti.app.products.courseware_reports.reports import _build_buckets_options
from nti.app.products.courseware_reports.reports import _assignment_stat_for_column
from nti.app.products.courseware_reports.reports import _do_get_containers_in_course
from nti.app.products.courseware_reports.reports import _get_self_assessments_for_course

from nti.app.products.courseware_reports.views import CHART_COLORS

from nti.app.products.courseware_reports.views.participation_views import ForumParticipationReportPdf

from nti.app.products.courseware_reports.views.view_mixins import _AbstractReportView

from nti.app.products.gradebook.interfaces import IGradeBook
from nti.app.products.gradebook.assignments import get_course_assignments

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.common import get_course_content_units

from nti.dataserver.interfaces import IDeletedObjectPlaceholder

from nti.zope_catalog.catalog import ResultSet


_EngagementPerfStat = \
    namedtuple('_EngagementPerfStat',
               ('first', 'second', 'third', 'fourth'))

_EngagementQuartileStat = \
    namedtuple('_EngagementQuartileStat',
               ('name', 'count', 'value', 'assignment_stat'))

_EngagementStats = \
    namedtuple('_EngagmentStats',
               ('for_credit', 'non_credit', 'aggregate'))

_EngagementStat = \
    namedtuple('_EngagementStat',
               ('name', 'count', 'unique_count', 'unique_perc_s', 'color'))

_NoteStat = namedtuple('_NoteStat',
                       ('shared_public', 'shared_course', 'shared_other'))


@view_config(context=ICourseInstance,
             name=VIEW_COURSE_SUMMARY)
class CourseSummaryReportPdf(_AbstractReportView):

    report_title = _('Course Summary Report')

    note_aggregator = None
    comment_aggregator = None
    highlight_aggregator = None
    assessment_aggregator = None

    def _build_enrollment_info(self, options):
        options['count_for_credit'] = len(self.for_credit_student_usernames)
        options['count_open'] = len(self.open_student_usernames)
        options['count_total'] = options[
            'count_for_credit'] + options['count_open']

    @Lazy
    def _self_assessments(self):
        self_assessments = _get_self_assessments_for_course(self.course)
        return self_assessments

    @Lazy
    def _self_assessment_qsids(self):
        """
        Map ntiid to question set.
        """
        self_assessment_qsids = {x.ntiid: x for x in self._self_assessments}
        return self_assessment_qsids

    @Lazy
    def _self_assessment_submissions(self):
        """
        Return the self-assessments and submission for the course.
        """
        md_catalog = self.md_catalog
        self_assessment_containerids = {x.__parent__.ntiid for x in self._self_assessments
                                        if hasattr(x.__parent__, 'ntiid')}

        # We can find the self-assessments the student submitted in a few ways
        # one would be to look at the user's contained data for each containerID
        # of the self assessment and see if there is an IQAssessedQuestionSet.
        # Another would be to find all IQAssessedQuestionSets the user has completed
        # using the catalog and match them up by IDs. This might be slightly slower, but it
        # has the advantage of not knowing anything about storage.
        intids_of_submitted_qsets = md_catalog['mimeType'].apply(
            {'any_of': ('application/vnd.nextthought.assessment.assessedquestionset',)})

        intids_of_submitted_qsets_by_students = \
            md_catalog.family.IF.intersection(intids_of_submitted_qsets,
                                              self.intids_created_by_students)

        # As opposed to what we do for the individual student, we
        # filter these by content unit ids. This won't filter out as many
        # submissions as filtering by container ids would, but it should
        # still improve performance somewhat.
        content_units = get_course_content_units(self.context)
        content_unit_ids = [x.ntiid for x in content_units]

        intids_of_objects_in_content_units = \
            md_catalog['containerId'].apply(
                {'any_of': content_unit_ids})

        intids_in_content_units = md_catalog.family.IF.intersection(intids_of_objects_in_content_units,
                                                                    intids_of_submitted_qsets_by_students)

        qsets_by_student_in_course = ResultSet(
            intids_in_content_units, self.uidutil)
        return qsets_by_student_in_course

    def _build_self_assessment_data(self, options):
        title_to_count = dict()

        for asm in self._self_assessments:
            accum = _TopCreators(self)
            accum.aggregate_creators = self.assessment_aggregator
            accum.title = asm.title or getattr(asm.__parent__, 'title', None)
            title_to_count[asm.ntiid] = accum

        for submission in self._self_assessment_submissions:
            # Content may have changed such that we have an orphaned question
            # set; move on.
            if submission.questionSetId in self._self_assessment_qsids:
                asm = self._self_assessment_qsids[submission.questionSetId]
                title_to_count[asm.ntiid].incr_username(
                    submission.creator.username)

        options['self_assessment_data'] = sorted(title_to_count.values(),
                                                 key=lambda x: x.title)

    def _get_containers_in_course(self):
        return _do_get_containers_in_course(self.course)

    def _build_engagement_data(self, options):
        md_catalog = self.md_catalog
        intersection = md_catalog.family.IF.intersection

        intids_of_notes = md_catalog['mimeType'].apply(
            {'any_of': ('application/vnd.nextthought.note',)})
        intids_of_hls = md_catalog['mimeType'].apply(
            {'any_of': ('application/vnd.nextthought.highlight',)})

        intids_of_notes = intersection(intids_of_notes,
                                       self.intids_created_by_everyone)
        intids_of_hls = intersection(intids_of_hls,
                                     self.intids_created_by_everyone)

        # all_notes = intids_of_notes
        # all_hls = intids_of_hls
        containers_in_course = self._get_containers_in_course()

        # Now we should have our whole tree of ntiids, intersect with our vals
        intids_of_objects_in_course_containers = md_catalog[
            'containerId'].apply({'any_of': containers_in_course})

        intids_of_notes = intersection(intids_of_notes,
                                       intids_of_objects_in_course_containers)
        intids_of_hls = intersection(intids_of_hls,
                                     intids_of_objects_in_course_containers)

        # We could filter notes and highlights (exclude deleted)
        notes = ResultSet(intids_of_notes, self.uidutil)
        note_creators = _TopCreators(self)
        note_creators.aggregate_creators = self.note_aggregator

        for note in notes:
            note_creators.incr_username(note.creator.username)

        for_credit_note_count = note_creators.for_credit_total
        non_credit_note_count = note_creators.non_credit_total
        total_note_count = note_creators.total

        for_credit_unique_note = note_creators.unique_contributors_for_credit
        for_credit_perc_s_note = note_creators.for_credit_percent_contributed_str()

        non_credit_unique_note = note_creators.unique_contributors_non_credit
        non_credit_perc_s_note = note_creators.non_credit_percent_contributed_str()

        total_unique_note = note_creators.unique_contributors
        total_perc_s_note = note_creators.percent_contributed_str()

        # Highlights
        highlights = ResultSet(intids_of_hls, self.uidutil)
        hl_creators = _TopCreators(self)
        hl_creators.aggregate_creators = self.highlight_aggregator
        for hl in highlights:
            hl_creators.incr_username(hl.creator.username)

        for_credit_hl_count = hl_creators.for_credit_total
        non_credit_hl_count = hl_creators.non_credit_total
        total_hl_count = hl_creators.total

        for_credit_unique_hl = hl_creators.unique_contributors_for_credit
        for_credit_perc_s_hl = hl_creators.for_credit_percent_contributed_str()

        non_credit_unique_hl = hl_creators.unique_contributors_non_credit
        non_credit_perc_s_hl = hl_creators.non_credit_percent_contributed_str()

        total_unique_hl = hl_creators.unique_contributors
        total_perc_s_hl = hl_creators.percent_contributed_str()

        # Discussions/comments
        discussion_creators = _TopCreators(self)
        comment_creators = _TopCreators(self)

        for forum in self.course.Discussions.values():
            for discussion in forum.values():
                discussion_creators.incr_username(discussion.creator.username)
                for comment in discussion.values():
                    if not IDeletedObjectPlaceholder.providedBy(comment):
                        comment_creators.incr_username(
                            comment.creator.username)

        # Discussions
        for_credit_discussion_count = discussion_creators.for_credit_total
        non_credit_discussion_count = discussion_creators.non_credit_total
        total_discussion_count = discussion_creators.total

        for_credit_unique_discussion = discussion_creators.unique_contributors_for_credit
        for_credit_perc_s_discussion = discussion_creators.for_credit_percent_contributed_str()

        non_credit_unique_discussion = discussion_creators.unique_contributors_non_credit
        non_credit_perc_s_discussion = discussion_creators.non_credit_percent_contributed_str()

        total_unique_discussion = discussion_creators.unique_contributors
        total_perc_s_discussion = discussion_creators.percent_contributed_str()

        # Comments
        for_credit_comment_count = comment_creators.for_credit_total
        non_credit_comment_count = comment_creators.non_credit_total
        total_comment_count = comment_creators.total

        for_credit_unique_comment = comment_creators.unique_contributors_for_credit
        for_credit_perc_s_comment = comment_creators.for_credit_percent_contributed_str()

        non_credit_unique_comment = comment_creators.unique_contributors_non_credit
        non_credit_perc_s_comment = comment_creators.non_credit_percent_contributed_str()

        total_unique_comment = comment_creators.unique_contributors
        total_perc_s_comment = comment_creators.percent_contributed_str()

        note_color = CHART_COLORS[0]
        hl_color = CHART_COLORS[5]
        discussion_color = CHART_COLORS[2]
        comments_color = CHART_COLORS[1]

        for_credit_notes = _EngagementStat(
            'Notes', for_credit_note_count, for_credit_unique_note, for_credit_perc_s_note, note_color)
        for_credit_hls = _EngagementStat(
            'Highlights', for_credit_hl_count, for_credit_unique_hl, for_credit_perc_s_hl, hl_color)
        for_credit_discussions = _EngagementStat(
            'Discussions Created', for_credit_discussion_count, for_credit_unique_discussion, for_credit_perc_s_discussion, discussion_color)
        for_credit_comments = _EngagementStat(
            'Discussion Comments', for_credit_comment_count, for_credit_unique_comment, for_credit_perc_s_comment, comments_color)
        for_credit_list = [for_credit_notes, for_credit_hls,
                           for_credit_discussions, for_credit_comments]
        activity = sum([x.count for x in for_credit_list])
        for_credit_stats = for_credit_list if activity else []

        non_credit_notes = _EngagementStat(
            'Notes', non_credit_note_count, non_credit_unique_note, non_credit_perc_s_note, note_color)
        non_credit_hls = _EngagementStat(
            'Highlights', non_credit_hl_count, non_credit_unique_hl, non_credit_perc_s_hl, hl_color)
        non_credit_discussions = _EngagementStat(
            'Discussions Created', non_credit_discussion_count, non_credit_unique_discussion, non_credit_perc_s_discussion, discussion_color)
        non_credit_comments = _EngagementStat(
            'Discussion Comments', non_credit_comment_count, non_credit_unique_comment, non_credit_perc_s_comment, comments_color)
        non_credit_list = [non_credit_notes, non_credit_hls,
                           non_credit_discussions, non_credit_comments]
        activity = sum([x.count for x in non_credit_list])
        non_credit_stats = non_credit_list if activity else []

        total_notes = _EngagementStat(
            'Notes', total_note_count, total_unique_note, total_perc_s_note, note_color)
        total_hls = _EngagementStat(
            'Highlights', total_hl_count, total_unique_hl, total_perc_s_hl, hl_color)
        total_discussions = _EngagementStat(
            'Discussions Created', total_discussion_count, total_unique_discussion, total_perc_s_discussion, discussion_color)
        total_comments = _EngagementStat(
            'Discussion Comments', total_comment_count, total_unique_comment, total_perc_s_comment, comments_color)
        aggregate_list = [
            total_notes, total_hls, total_discussions, total_comments]
        activity = sum([x.count for x in aggregate_list])
        aggregate_stats = aggregate_list if activity else []

        options['engagement_data'] = _EngagementStats(
            for_credit_stats, non_credit_stats, aggregate_stats)

    def _build_assignment_data(self, predicate=None):
        gradebook = IGradeBook(self.course)
        assignment_catalog = get_course_assignments(self.course)

        stats = list()
        for asg in assignment_catalog:
            # XXX: Seems like this should be assignment filter.
            # If published with available dates, we'll expose them in the
            # report.
            if not asg.is_published():
                continue
            column = gradebook.getColumnForAssignmentId(asg.ntiid)
            if column is not None:
                stats.append(
                    _assignment_stat_for_column(self, column, predicate))

        stats.sort(key=lambda x: (x.due_date is None, x.due_date, x.title))
        return stats

    def _build_top_commenters(self, options):

        forum_stats = dict()
        agg_creators = _TopCreators(self)
        agg_creators.aggregate_creators = self.comment_aggregator

        for key, forum in self.course.Discussions.items():
            forum_stat = forum_stats[key] = dict()
            forum_stat['forum'] = forum
            forum_view = ForumParticipationReportPdf(forum, self.request)
            forum_view.agg_creators = agg_creators
            forum_view.options = forum_stat

            last_mod_ts = forum.NewestDescendantCreatedTime
            last_mod_time = _adjust_timestamp(
                last_mod_ts) if last_mod_ts > 0 else None
            forum_stat['last_modified'] = _format_datetime(
                last_mod_time) if last_mod_time else 'N/A'

            forum_view.for_credit_student_usernames = self.for_credit_student_usernames
            forum_view()
            forum_stat['discussion_count'] = len(
                self.filter_objects(forum.values()))
            forum_stat['total_comments'] = sum(
                [x.comment_count for x in forum_stat['comment_count_by_topic']])

        # Need to accumulate these
        # TODO: rework this
        acc_week = self.family.II.BTree()

        # Aggregate weekly numbers
        for key, stat in forum_stats.items():
            forum_stat = stat['all_forum_participation']
            by_week = forum_stat.forum_objects_by_week_number
            for week, val in by_week.items():
                if week in acc_week:
                    acc_week[week] += val
                else:
                    acc_week[week] = val

        # Now we have to come up with our categories
        accum_dates_list = (x['group_dates'] for x in forum_stats.values())
        accum_dates = list(chain.from_iterable(accum_dates_list))
        accum_dates = sorted(accum_dates)

        # Now get our date fields
        date_accum = _DateCategoryAccum(self.course_start_date)
        dates = date_accum.accum_all(accum_dates)

        new_buckets = _CommonBuckets(None, acc_week, None, dates)
        agg_stat = _build_buckets_options({}, new_buckets)
        options['aggregate_forum_stats'] = agg_stat

        options['forum_stats'] = [x[1] for x in sorted(forum_stats.items())]

        options['aggregate_creators'] = agg_creators
        options['top_commenters_colors'] = CHART_COLORS

    def __call__(self):
        self._check_access()
        options = self.options

        self._build_engagement_data(options)
        self._build_enrollment_info(options)
        self._build_self_assessment_data(options)
        options['assignment_data'] = self._build_assignment_data()
        self._build_top_commenters(options)

        video_usage = IVideoUsageStats(self.context, None)
        if video_usage is not None:
            options['top_video_usage'] = video_usage.get_top_stats()
            options['all_video_usage'] = video_usage.get_stats()

        resource_usage = IResourceUsageStats(self.context, None)
        if resource_usage is not None:
            options['top_resource_usage'] = resource_usage.get_top_stats()
            options['all_resource_usage'] = resource_usage.get_stats()

        return options

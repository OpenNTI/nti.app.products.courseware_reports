#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import csv

from io import BytesIO

from zope.security.management import checkPermission

from collections import namedtuple

from datetime import datetime

from nti.app.products.courseware_reports import MessageFactory as _

from pyramid.view import view_config

from pyramid.httpexceptions import HTTPForbidden

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.app.products.courseware_reports import VIEW_SELF_ASSESSMENT_SUMMARY

from nti.app.products.courseware_reports.reports import TopCreators

from nti.app.products.courseware_reports.views.summary_views import CourseSummaryReportPdf

from nti.dataserver.authorization import is_admin

from nti.dataserver.users.interfaces import IFriendlyNamed

from nti.dataserver.users.users import User

from nti.app.products.courseware_reports.interfaces import ACT_VIEW_REPORTS

from nti.app.products.courseware_reports.reports import _adjust_date

from nti.app.products.courseware_reports.reports import _format_datetime


_SelfAssessmentCompletion = namedtuple( '_SelfAssessmentCompletion',
                                        ('title', 'question_count', 'students'))

_StudentSelfAssessmentCompletion = namedtuple( '_SelfAssessmentCompletion',
                                             ('display', 'username',
                                              'count', 'unique_attempts',
                                              'assessment_count'))

_StudentSelfAssessmentCompletionCSV = namedtuple( '_SelfAssessmentCompletion',
                                               ('display', 'alias', 'username',
                                                'count', 'unique_attempts',
                                                'assessment_count', 'final_assessment_submitted_time'))

logger = __import__('logging').getLogger(__name__)

def _tx_string(s):
    if s is not None and isinstance(s, unicode):
        s = s.encode('utf-8')
    return s

def _write(data, writer, stream):
    writer.writerow([_tx_string(x) for x in data])
    return stream

class AbstractSelfAssessmentReport(CourseSummaryReportPdf):

    def _build_qset_to_user_submission(self):
        """
        For each submission, gather the questions completed as well as the
        submitted question sets per student.
        """
        # qset.ntiid -> username -> submitted question ntiid set
        qsid_to_user_submission_set = {}
        user_completed_set = {}
        user_submitted_set = {}
        user_to_completion_date_set = {}
        # Iterate through submission, gathering all question_ids with response.
        for submission in self._self_assessment_submissions:
            # Content may have changed such that we have an orphaned question set; move on.
            if submission.questionSetId in self._self_assessment_qsids:
                asm = self._self_assessment_qsids[submission.questionSetId]
                username = submission.creator.username.lower()
                user_submitted = user_submitted_set.setdefault( username, set() )
                user_submitted.add(asm.ntiid)
                
                user_to_completion_date = user_to_completion_date_set.setdefault( username, {} )

                if asm.ntiid in user_to_completion_date:
                    user_to_completion_date[asm.ntiid].append(submission.createdTime)
                else:
                    user_to_completion_date[asm.ntiid] = [submission.createdTime]
                
                if asm.ntiid in user_completed_set.get( username, {} ):
                    continue
                student_sets = qsid_to_user_submission_set.setdefault( asm.ntiid, {} )
                student_set = student_sets.setdefault( username, set() )
                completed = True
                for question in submission.questions:
                    for part in question.parts:
                        if part.submittedResponse is not None:
                            student_set.add( question.questionId )
                        else:
                            completed = False
                if completed:
                    user_completed = user_completed_set.setdefault( username, set() )
                    user_completed.add( asm.ntiid )
            
        return qsid_to_user_submission_set, user_submitted_set, user_to_completion_date_set


@view_config(context=ICourseInstance,
             name=VIEW_SELF_ASSESSMENT_SUMMARY)
class SelfAssessmentSummaryReportPdf(AbstractSelfAssessmentReport):
    """
    A basic SelfAssessment report for a course, including summary data on
    overall self-assessment usage and per self-assessment completion data.
    """

    report_title = _(u'Self Assessment Report')

    def _get_by_student_stats(self, stats, assessment_names, student_names,
                              user_submission_sets, assessment_count):
        """
        Get our sorted stats, including zero'd stats for users without self
        assessment submissions.
        """
        assessment_usernames = {x.lower() for x in assessment_names}
        missing_usernames = student_names - assessment_usernames
        stats.extend( (self.build_user_info( username ) for username in missing_usernames) )
        stats = sorted( stats )
        result = []
        for user_stats in sorted(stats):
            username = user_stats.username
            user_completed_count = len(user_submission_sets.get(username, {})) or None
            user_completion = _StudentSelfAssessmentCompletion(user_stats.display,
                                                               username,
                                                               user_stats.count,
                                                               user_completed_count,
                                                               assessment_count)
            result.append(user_completion)
        return result

    def _get_self_assessments_by_student(self, user_submission_sets, assessment_count):
        """
        Get our by student stats for open and credit students.
        """
        open_stats = self._get_by_student_stats( self.assessment_aggregator.open_stats,
                                                 self.assessment_aggregator.non_credit_keys(),
                                                 self.open_student_usernames,
                                                 user_submission_sets,
                                                 assessment_count )
        credit_stats = self._get_by_student_stats( self.assessment_aggregator.credit_stats,
                                                   self.assessment_aggregator.for_credit_keys(),
                                                   self.for_credit_student_usernames,
                                                   user_submission_sets,
                                                   assessment_count )
        return open_stats, credit_stats

    def _get_completion_student_data( self, submission_data, student_names, question_count ):
        """
        Build out student infos from the given student population and submissions.
        """
        results = []
        for username in student_names:
            submitted_count = len( submission_data.get( username, () ))
            perc = "%0.1f" % (submitted_count/question_count * 100.0) if question_count else 'NA'
            student_info = self.build_user_info(username, count=submitted_count, perc=perc)
            results.append( student_info )
        results = sorted( results )
        return results

    def _get_self_assessments_completion(self):
        """
        By self assessment, gather how many questions the student submitted to
        return completion stats.
        """
        # qset.ntiid -> username -> submitted question ntiid set
        qsid_to_user_submission_set, user_submission_sets, user_to_completion_date_set = self._build_qset_to_user_submission()

        credit_results = list()
        open_results = list()
        # Now build our completion data.
        for asm in self._self_assessments:
            title = asm.title or getattr( asm.__parent__, 'title', None )
            question_count = getattr( asm, 'draw', None ) or len( asm.questions )
            qset_submission_data = qsid_to_user_submission_set.get( asm.ntiid, {} )
            # Open
            open_students = self._get_completion_student_data( qset_submission_data,
                                                               self.open_student_usernames,
                                                               question_count )
            if open_students:
                open_completion = _SelfAssessmentCompletion( title, question_count,
                                                             open_students )
                open_results.append( open_completion )
            # Credit
            credit_students = self._get_completion_student_data( qset_submission_data,
                                                                 self.for_credit_student_usernames,
                                                                 question_count )
            if credit_students:
                credit_completion = _SelfAssessmentCompletion( title, question_count,
                                                               credit_students )
                credit_results.append( credit_completion )
        open_results = sorted( open_results, key=lambda x: x.title )
        credit_results = sorted( credit_results, key=lambda x: x.title )
        return open_results, credit_results, user_submission_sets

    def __call__(self):
        self._check_access()
        options = self.options
        self.assessment_aggregator = TopCreators(self)

        self._build_self_assessment_data( options )
        assessment_count = len(options['self_assessment_data'])
        open_completion, credit_completion, user_submission_sets = self._get_self_assessments_completion()
        options['self_assessment_open_completion'] = open_completion
        options['self_assessment_credit_completion'] = credit_completion
        open_stats, credit_stats = self._get_self_assessments_by_student(user_submission_sets,
                                                                         assessment_count)
        options['self_assessment_non_credit'] = open_stats
        options['self_assessment_for_credit'] = credit_stats
        self._build_enrollment_info(options)
        return options

@view_config(route_name='objects.generic.traversal',
             name='SelfAssessmentReportCSV',
             renderer='rest',
             request_method='GET',
             context=ICourseInstance)
class SelfAssessmentReportCSV(AbstractSelfAssessmentReport):
    """
    A Self-Assessment report csv
    """

    report_title = _(u'Self Assessment CSV report')
    # 
    def __init__(self, context, request):
        self.context = context
        self.request = request
        self.options = {}

        if 'remoteUser' in request.params:
            self.remoteUser = request.params['remoteUser']
        else:
            self.remoteUser = self.getRemoteUser()

    def _get_by_student_stats(self, stats, assessment_names, student_names,
                              user_submission_sets, assessment_count, user_to_completion_date_set):
        """
        Get our sorted stats, including zero'd stats for users without self
        assessment submissions.
        """
        assessment_usernames = {x.lower() for x in assessment_names}
        missing_usernames = student_names - assessment_usernames
        stats.extend( (self.build_user_info( username ) for username in missing_usernames) )
        result = []
        
        for user_stats in stats:
            username = user_stats.username
            
            user = User.get_user(username)

            friendlyName = IFriendlyNamed(user)

            completion_date_map = user_to_completion_date_set.get(username, {}) or None
            
            user_completed_count = len(user_submission_sets.get(username, {})) or None

            final_assessment_submitted_time = None

            completion_date_set = []
            
            if completion_date_map:
                for completion_date_key, completion_date_value in completion_date_map.iteritems():
                    completion_date_set.append(min(completion_date_value))
            
                final_assessment_submitted_time = max(completion_date_set)
            
            user_completion = _StudentSelfAssessmentCompletionCSV(user_stats.display,
                                                               friendlyName.alias,
                                                               username,
                                                               user_stats.count,
                                                               user_completed_count,
                                                               assessment_count, final_assessment_submitted_time)
            result.append(user_completion)

        result = sorted(result, key=lambda x:x.final_assessment_submitted_time, reverse=True)
        
        return result

    def _get_self_assessments_by_student(self, user_submission_sets, assessment_count, user_to_completion_date_set):
        """
        Get our by student stats for open and credit students.
        """
        all_stats = self._get_by_student_stats( self.assessment_aggregator.all_stats,
                                                 self.assessment_aggregator.non_credit_keys(), 
                                                 self.open_student_usernames,
                                                 user_submission_sets,
                                                 assessment_count,
                                                 user_to_completion_date_set)
        return all_stats

    def __call__(self):
        self._check_access()
        options = self.options
        self.assessment_aggregator = TopCreators(self)
        self._build_self_assessment_data( options )

        assessment_count = len(options['self_assessment_data'])

        qsid_to_user_submission_set, user_submission_sets, user_to_completion_date_set = self._build_qset_to_user_submission()

        all_stats = self._get_self_assessments_by_student(user_submission_sets,
                                                                         assessment_count,
                                                                        user_to_completion_date_set)
        response = self.request.response
        response.content_encoding = 'identity'
        response.content_type = 'text/csv; charset=UTF-8'
        response.content_disposition = 'attachment; filename="self_assessment_report.csv"'

        stream = BytesIO()
        writer = csv.writer(stream)

        header_row = ['Display Name', 'Alias', 'User name', 'Total Assessment Attempts', 
                      'Unique Assessment Attempts', 'Total Assessment Count', 'Assessment Completion Date']
        
        _write(header_row, writer, stream)
        
        for stats in all_stats:
            time = stats.final_assessment_submitted_time
            if time:
                time = datetime.fromtimestamp(time)
                time = _format_datetime(_adjust_date(time))
            
            data_row = []
            data_row.append(stats.display)
            data_row.append(stats.alias)
            data_row.append(stats.username)
            data_row.append(stats.count)
            data_row.append(stats.unique_attempts)
            data_row.append(stats.assessment_count)
            data_row.append(time)
            _write(data_row, writer, stream)

        stream.flush()
        stream.seek(0)
        response.body_file = stream
        return response
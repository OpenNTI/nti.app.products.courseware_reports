#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import calling
from hamcrest import raises
from hamcrest import is_
from hamcrest import is_not
from hamcrest import has_key
from hamcrest import has_item
from hamcrest import assert_that
from hamcrest import has_entries
from hamcrest import has_entry
from hamcrest import has_properties
from hamcrest import none
from hamcrest import has_length
from hamcrest import contains_inanyorder
from hamcrest import ends_with

import csv
import datetime
import fudge

from pyramid import httpexceptions as hexc

from zope import component
from zope import interface
from zope import lifecycleevent

from nti.dataserver.users.users import User
from nti.dataserver.users.communities import Community
from nti.dataserver.users.friends_lists import DynamicFriendsList

from nti.app.products.courseware_reports.interfaces import IRosterReportSupplementalFields

from nti.app.products.courseware_reports.views.enrollment_views import AbstractEnrollmentReport
from nti.app.products.courseware_reports.views.enrollment_views import EnrollmentRecordsReportPdf

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.app.products.courseware.tests import PersistentInstructedCourseApplicationTestLayer

from nti.app.testing.application_webtest import ApplicationLayerTest

from nti.app.testing.decorators import WithSharedApplicationMockDS

from nti.app.testing.request_response import DummyRequest

from nti.contenttypes.courses.interfaces import ICourseCatalog
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry
from nti.contenttypes.courses.interfaces import ICourseEnrollmentManager
from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.dataserver.users.common import set_user_creation_site

from nti.dataserver.tests import mock_dataserver


class TestEnrollmentRecordsReport(ApplicationLayerTest):

    layer = PersistentInstructedCourseApplicationTestLayer

    default_origin = b'http://janux.ou.edu'
    course_ntiid = 'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'

    pdf_url = '/dataserver2/++etc++hostsites/janux.ou.edu/++etc++site/Courses/@@EnrollmentRecordsReport?format=application%2Fpdf'
    csv_url = '/dataserver2/++etc++hostsites/janux.ou.edu/++etc++site/Courses/@@EnrollmentRecordsReport?format=text%2Fcsv'

    @WithSharedApplicationMockDS(users=(u'test@nextthought.com',), testapp=True, default_authenticate=False)
    def testEnrollmentRecordsReport(self):
        self.testapp.post_json(self.pdf_url, status=401, extra_environ=self._make_extra_environ(username=None))
        self.testapp.post_json(self.pdf_url, status=200, extra_environ=self._make_extra_environ(username='test@nextthought.com'))

        self.testapp.post_json(self.csv_url, status=401, extra_environ=self._make_extra_environ(username=None))
        self.testapp.post_json(self.csv_url, status=200, extra_environ=self._make_extra_environ(username='test@nextthought.com'))

    def _add_site_admin(self, username):
        url = '/dataserver2/SiteAdmins'
        self.testapp.post_json(url, {'username': username}, status=200, extra_environ=self._make_extra_environ(username='test@nextthought.com'))

    def _create_admin_level(self, admin_level='test_admin_key_report'):
        url = '/dataserver2/++etc++hostsites/janux.ou.edu/++etc++site/Courses/@@AdminLevels'
        admin_levels = self.testapp.get(url, extra_environ=self._make_extra_environ(username='test@nextthought.com')).json_body['Items']
        if admin_level not in admin_levels:
            self.testapp.post_json(url, {'key': admin_level}, status=200, extra_environ=self._make_extra_environ(username='test@nextthought.com'))

    def _creat_course(self, id, title=None, admin_level='test_admin_key_report'):
        url = '/dataserver2/++etc++hostsites/janux.ou.edu/++etc++site/Courses/%s' % (admin_level)
        title = title or id
        data = {"ProviderUniqueID":id,"title":title,"identifier":id,"key":id}
        return self.testapp.post_json(url, data, status=200, extra_environ=self._make_extra_environ(username='test@nextthought.com')).json_body['NTIID']

    def _open_course(self, course_ntiid):
        url = '/dataserver2/Objects/%s/CourseCatalogEntry' % course_ntiid
        self.testapp.put_json(url, {'Preview': False, 'is_non_public': False}, extra_environ=self._make_extra_environ(username='test@nextthought.com'))

    def _add_course_instructor(self, username, course_ntiid, admin_level='test_admin_key_report'):
        url = '/dataserver2/++etc++hostsites/janux.ou.edu/++etc++site/Courses/%s/%s/@@Instructors' % (admin_level, course_ntiid)
        self.testapp.post_json(url, {'user': username}, status=204, extra_environ=self._make_extra_environ(username='test@nextthought.com'))

    def _init_data(self):
        self.extra_environ_user001 = self._make_extra_environ(username='user001')
        self.extra_environ_user002 = self._make_extra_environ(username='user002')
        self.extra_environ_user003 = self._make_extra_environ(username='user003')
        self.extra_environ_siteadmin001 = self._make_extra_environ(username='siteadmin001')
        self.extra_environ_instructor001 = self._make_extra_environ(username="instructor001")
        self.extra_environ_admin = self._make_extra_environ(username='test@nextthought.com')

        self.HEADER_GROUP_BY_COURSE = 'Course Title,Course Provider Unique ID,Course Start Date,Course Instructors,Name,User Name,Email,Date Enrolled,Last Seen,Completion,Completed Successfully'
        self.HEADER_GROUP_BY_USER = 'Name,User Name,Email,Course Title,Course Provider Unique ID,Course Start Date,Course Instructors,Date Enrolled,Last Seen,Completion,Completed Successfully'

    def _assert_csv_reports(self, groupByCourse, course_ntiids):
        params = {'groupByCourse': groupByCourse}
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_admin)
        assert_that(result.body.splitlines(), has_length(5))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_siteadmin001)
        assert_that(result.body.splitlines(), has_length(5))
        # instructor can access instructed courses.
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_instructor001)
        assert_that(result.body.splitlines(), has_length(3))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_user001)
        assert_that(result.body.splitlines(), has_length(3))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_user002)
        assert_that(result.body.splitlines(), has_length(2))

        params = {'groupByCourse': groupByCourse, 'entity_ids': ['user001', 'user003']}
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_admin)
        assert_that(result.body.splitlines(), has_length(4))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_siteadmin001)
        assert_that(result.body.splitlines(), has_length(4))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_user001)
        assert_that(result.body.splitlines(), has_length(3))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_user002)
        assert_that(result.body.splitlines(), has_length(1))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_user003)
        assert_that(result.body.splitlines(), has_length(2))

        params = {'groupByCourse': groupByCourse, 'entity_ids': ['user001', 'user003'], 'course_ntiids': [course_ntiids[0]]}
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_admin)
        assert_that(result.body.splitlines(), has_length(2))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_user002)
        assert_that(result.body.splitlines(), has_length(1))
        result = self.testapp.post_json(self.csv_url, params, status=403, extra_environ=self.extra_environ_user003)
        assert_that(result.json_body['message'], is_('Can not access course (title=course_1).'))

        params = {'groupByCourse': groupByCourse, 'entity_ids': ['user001']}
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_siteadmin001)
        assert_that(result.body.splitlines(), has_length(3))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_user001)
        assert_that(result.body.splitlines(), has_length(3))
        # user001 enrolled in 2 courses, but instructor001 only instruct course_1
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_instructor001)
        assert_that(result.body.splitlines(), has_length(2))
        result = self.testapp.post_json(self.csv_url, params, status=200, extra_environ=self.extra_environ_user002)
        assert_that(result.body.splitlines(), has_length(1))

    def _assert_supplemental_info(self):
        @interface.implementer(IRosterReportSupplementalFields)
        class _TestReportSupplementalFields(object):

            def get_user_fields(self, user):
                return {'username': user.username, 'lastLoginTime': user.lastLoginTime}

            def get_field_display_values(self):
                return {'username': "UserName", 'lastLoginTime': "LastLogin"}

            def get_ordered_fields(self):
                return ['username', 'lastLoginTime']

        fields_utility = _TestReportSupplementalFields()
        component.getGlobalSiteManager().registerUtility(fields_utility, IRosterReportSupplementalFields)

        result = self.testapp.post_json(self.csv_url, {'groupByCourse': True}, status=200, extra_environ=self.extra_environ_user002)
        result = result.body.splitlines()
        assert_that(result[0], is_(self.HEADER_GROUP_BY_COURSE + ',UserName,LastLogin'))
        assert_that(result[1], ends_with('N/A,,user002,0'))

        result = self.testapp.post_json(self.csv_url, {'groupByCourse': False}, status=200, extra_environ=self.extra_environ_user002)
        result = result.body.splitlines()
        assert_that(result[0], is_(self.HEADER_GROUP_BY_USER + ',UserName,LastLogin'))
        assert_that(result[1], ends_with('N/A,,user002,0'))

        component.getGlobalSiteManager().unregisterUtility(fields_utility)

        result = self.testapp.post_json(self.csv_url, {'groupByCourse': True}, status=200, extra_environ=self.extra_environ_user002)
        result = result.body.splitlines()
        assert_that(result[0], is_(self.HEADER_GROUP_BY_COURSE))
        assert_that(result[1], ends_with('N/A,'))

        result = self.testapp.post_json(self.csv_url, {'groupByCourse': False}, status=200, extra_environ=self.extra_environ_user002)
        result = result.body.splitlines()
        assert_that(result[0], is_(self.HEADER_GROUP_BY_USER))
        assert_that(result[1], ends_with('N/A,'))

    @WithSharedApplicationMockDS(users=(u'user001', u'user002', u'user003', u'user004', u'instructor001', u'siteadmin001', u'test@nextthought.com'), testapp=True, default_authenticate=False)
    def testEnrollmentRecordsReportCSV(self):
        self._init_data()
        admin_level = u'test_admin_key'
        with mock_dataserver.mock_db_trans(self.ds, site_name='janux.ou.edu'):
            for username in (u'user001', u'user002', u'user003', u'user004', u'instructor001', u'siteadmin001', u'test@nextthought.com'):
                user = User.get_user(username)
                set_user_creation_site(user, 'janux.ou.edu')
                lifecycleevent.modified(user)

        self._create_admin_level()
        self._add_site_admin(u'siteadmin001')

        course_ntiid1 = self._creat_course(id=u"course_1")
        course_ntiid2 = self._creat_course(id=u"course_2")
        self._open_course(course_ntiid1)
        self._open_course(course_ntiid2)

        self._add_course_instructor(u'instructor001', u'course_1')

        # no enrollments, just header
        result = self.testapp.post_json(self.csv_url, {'groupByCourse': True}, status=200, extra_environ=self.extra_environ_admin)
        assert_that(result.body.splitlines(), has_length(1))
        assert_that(result.body.splitlines()[0], is_(self.HEADER_GROUP_BY_COURSE))

        result = self.testapp.post_json(self.csv_url, {'groupByCourse': False}, status=200, extra_environ=self.extra_environ_admin)
        assert_that(result.body.splitlines(), has_length(1))
        assert_that(result.body.splitlines()[0], is_(self.HEADER_GROUP_BY_USER))

        with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
            user1 = User.get_user('user001')
            user2 = User.get_user('user002')
            user3 = User.get_user('user003')
            course = find_object_with_ntiid(course_ntiid1)
            enrollment_manager = ICourseEnrollmentManager(course)
            enrollment_manager.enroll(user1)
            enrollment_manager.enroll(user2)
         
            course2 = find_object_with_ntiid(course_ntiid2)
            ICourseEnrollmentManager(course2).enroll(user1)
            ICourseEnrollmentManager(course2).enroll(user3)

        # Group by course
        self._assert_csv_reports(groupByCourse=True, course_ntiids=[course_ntiid1, course_ntiid2])
        # Group by user
        self._assert_csv_reports(groupByCourse=False, course_ntiids=[course_ntiid1, course_ntiid2])

        self._assert_supplemental_info()


class TestEnrollmentRecordsReportPdf(ApplicationLayerTest):

    @WithSharedApplicationMockDS(users=True, testapp=True, default_authenticate=True)
    def test_params(self):
        with mock_dataserver.mock_db_trans(self.ds):
            catalog = component.getUtility(ICourseCatalog)
            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={}, method='POST'))
            assert_that(view, has_properties({'_params': has_length(0),
                                              'groupByCourse': True,
                                              'show_supplemental_info': False,
                                              'input_users': None,
                                              'input_entries': None,
                                              'completionNotBefore': None,
                                              'completionNotAfter': None}))

            params = {'groupByCourse': False,
                      'entity_ids': ['user001'],
                      'course_ntiids': None,
                      'completionNotBefore': 1545091200,
                      'completionNotAfter': 1545112800}
            request = DummyRequest(json_body=params, method='POST')
            view = EnrollmentRecordsReportPdf(catalog, request)
            # For PDF report, we don't show supplemental info now.
            assert_that(view, has_properties({'groupByCourse': False, 'show_supplemental_info': False}))
            assert_that(view._params, has_entries({'entity_ids': ['user001'], 'course_ntiids': None}))
            assert_that(view.completionNotBefore.strftime('%Y-%m-%d %H:%M:%S'), is_('2018-12-18 00:00:00'))
            assert_that(view.completionNotAfter.strftime('%Y-%m-%d %H:%M:%S'), is_('2018-12-18 06:00:00'))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'course_ntiids': 'abc'}, method='POST'))
            assert_that(calling(getattr).with_args(view, '_params'), raises(hexc.HTTPUnprocessableEntity))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotBefore': 'abc'}, method='POST'))
            assert_that(calling(getattr).with_args(view, 'completionNotBefore'), raises(hexc.HTTPUnprocessableEntity))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotAfter': ''}, method='POST'))
            assert_that(calling(getattr).with_args(view, 'completionNotAfter'), raises(hexc.HTTPUnprocessableEntity))

    @WithSharedApplicationMockDS(users=(u'user001', u'user002',u'user003',u'user004',u'user005',u'user006'), testapp=True, default_authenticate=False)
    def test_input_users(self):
        with mock_dataserver.mock_db_trans(self.ds):
            user1 = User.get_user('user001')
            user2 = User.get_user('user002')
            user3 = User.get_user('user003')
            user4 = User.get_user('user004')
            user5 = User.get_user('user005')
            community1 = Community.create_community( username='community1' )
            community2 = Community.create_community( username='community2' )

            # no entity_ids
            catalog = component.getUtility(ICourseCatalog)
            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':[]}, method='POST'))
            assert_that(view.input_users, is_(None))
            assert_that(view._get_users(), has_length(0))

            # should return all site users if entity_ids is not provided and groupByGroup is False.
            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':[], 'groupByCourse': 'false'}, method='POST'))
            assert_that(view.input_users, is_(None))
            assert_that(view._get_users(), has_length(7))

            # should return all site users if entity_ids is not provided and groupByGroup is False.
            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'groupByCourse': 'false'}, method='POST'))
            assert_that(view.input_users, is_(None))
            assert_that(view._get_users(), has_length(7))

            # user00x not found
            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':['user001', 'user00x', 'user002']}, method='POST'))
            assert_that(calling(getattr).with_args(view, 'input_users'), raises(hexc.HTTPUnprocessableEntity))

            # all users found
            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':['user001', 'user002']}, method='POST'))
            assert_that(view.input_users, has_length(2))

            # both communities have no members
            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':['community1', 'community2']}, method='POST'))
            assert_that(calling(getattr).with_args(view, 'input_users'), raises(hexc.HTTPUnprocessableEntity))

            user1.record_dynamic_membership(community1)
            user2.record_dynamic_membership(community1)

            user1.record_dynamic_membership(community2)
            user3.record_dynamic_membership(community2)

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':['community1']}, method='POST'))
            assert_that(view.input_users, contains_inanyorder(user1, user2))
            assert_that(view._get_users(), contains_inanyorder(user1, user2))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':['community1', 'community2']}, method='POST'))
            assert_that(view.input_users, contains_inanyorder(user1, user2, user3))

            dfl = DynamicFriendsList(username=u'dfl001')
            dfl.creator = user1
            user1.addContainedObject(dfl)
            dfl.addFriend(user4)
            dfl.addFriend(user5)
            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':[dfl.NTIID]}, method='POST'))
            assert_that(view.input_users, contains_inanyorder(user4, user5))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'entity_ids':['user003', 'community1', dfl.NTIID]}, method='POST'))
            assert_that(view.input_users, contains_inanyorder(user1, user2, user3, user4, user5))
            assert_that(view._get_users(), contains_inanyorder(user1, user2, user3, user4, user5))

    @WithSharedApplicationMockDS(users=True, testapp=True, default_authenticate=True)
    def test_predicate_with_progress(self):
        # notBefore is inclusive, notAfter is exclusive.
        with mock_dataserver.mock_db_trans(self.ds):
            catalog = component.getUtility(ICourseCatalog)
            now = datetime.datetime.utcfromtimestamp(100)
            complete_progress = fudge.Fake('Progress').has_attr(Completed=True, CompletedDate=now)
            incomplete_progress = fudge.Fake('Progress').has_attr(Completed=False)

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotBefore': None, 'completionNotAfter': None}))
            assert_that(view._predicate_with_progress(complete_progress), is_(True))
            assert_that(view._predicate_with_progress(incomplete_progress), is_(True))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotBefore': None, 'completionNotAfter': 100}))
            assert_that(view._predicate_with_progress(complete_progress), is_(False))
            assert_that(view._predicate_with_progress(incomplete_progress), is_(False))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotBefore': None, 'completionNotAfter': 101}))
            assert_that(view._predicate_with_progress(complete_progress), is_(True))
            assert_that(view._predicate_with_progress(incomplete_progress), is_(False))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotBefore': 100, 'completionNotAfter': 100}))
            assert_that(view._predicate_with_progress(complete_progress), is_(False))
            assert_that(view._predicate_with_progress(incomplete_progress), is_(False))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotBefore': 100, 'completionNotAfter': 101}))
            assert_that(view._predicate_with_progress(complete_progress), is_(True))
            assert_that(view._predicate_with_progress(incomplete_progress), is_(False))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotBefore': 100, 'completionNotAfter': None}))
            assert_that(view._predicate_with_progress(complete_progress), is_(True))
            assert_that(view._predicate_with_progress(incomplete_progress), is_(False))

            view = EnrollmentRecordsReportPdf(catalog, DummyRequest(json_body={'completionNotBefore': 101, 'completionNotAfter': None}))
            assert_that(view._predicate_with_progress(complete_progress), is_(False))
            assert_that(view._predicate_with_progress(incomplete_progress), is_(False))
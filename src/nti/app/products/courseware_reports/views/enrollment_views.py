#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import six
import gevent
import unicodecsv as csv

from collections import namedtuple

from datetime import datetime

from io import BytesIO

from nameparser import HumanName

from pyramid.config import not_

from pyramid import httpexceptions as hexc

from pyramid.view import view_config

from requests.structures import CaseInsensitiveDict

from zc.displayname.interfaces import IDisplayNameGenerator

from zope import component

from zope.cachedescriptors.property import Lazy

from zope.intid.interfaces import IIntIds

from zope.security.management import checkPermission

from nti.app.contenttypes.completion.adapters import CompletionContextProgressFactory

from nti.app.externalization.error import raise_json_error

from nti.app.externalization.view_mixins import ModeledContentUploadRequestUtilsMixin

from nti.app.products.courseware_reports import VIEW_ENROLLMENT_RECORDS_REPORT

from nti.app.products.courseware_reports import MessageFactory as _

from nti.app.products.courseware_reports.interfaces import ACT_VIEW_REPORTS
from nti.app.products.courseware_reports.interfaces import IRosterReportSupplementalFields

from nti.app.products.courseware_reports.views.view_mixins import AbstractReportView
from nti.app.products.courseware_reports.views.view_mixins import generate_semester

from nti.appserver.pyramid_authorization import has_permission

from nti.common.string import is_true

from nti.contenttypes.courses.interfaces import ICourseCatalog
from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry
from nti.contenttypes.courses.interfaces import ICourseEnrollments

from nti.contenttypes.courses.utils import is_hidden_tag
from nti.contenttypes.courses.utils import get_enrollments
from nti.contenttypes.courses.utils import is_course_instructor
from nti.contenttypes.courses.utils import get_enrollment_records

from nti.coremetadata.interfaces import IDeactivatedUser
from nti.coremetadata.interfaces import ILastSeenProvider

from nti.dataserver.authorization import ACT_CONTENT_EDIT
from nti.dataserver.authorization import is_admin
from nti.dataserver.authorization import is_site_admin

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import ICommunity
from nti.dataserver.interfaces import IDynamicSharingTargetFriendsList
from nti.dataserver.interfaces import ISiteAdminUtility

from nti.dataserver.users.interfaces import IFriendlyNamed

from nti.dataserver.users import User
from nti.dataserver.users import Entity

from nti.dataserver.users.utils import get_users_by_site
from nti.dataserver.users.utils import get_filtered_users_by_site

from nti.mailer.interfaces import IEmailAddressable

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.traversal.traversal import find_interface

logger = __import__('logging').getLogger(__name__)


CatalogEntryRecord = \
    namedtuple('CatalogEntryRecord',
               ('title', 'start_date', 'instructors', 'provider_unique_id', 'semester'))


class EnrollmentViewMixin(object):

    def __init__(self):
        # Cache required item providers for a course.
        self._cache_required_item_providers = dict()

    @Lazy
    def course_catalog(self):
        return component.queryUtility(ICourseCatalog)

    @Lazy
    def intids(self):
        return component.getUtility(IIntIds)

    @Lazy
    def show_supplemental_info(self):
        """
        Currently we only show additional user information in the CSV Reports, this will determine
        if we should calculate additional information combining with the supplemental_field_utility.
        """
        return False

    @Lazy
    def supplemental_field_utility(self):
        return component.queryUtility(IRosterReportSupplementalFields)

    def _add_name_info(self, user, user_dict, friendly_named=None):
        displayname = component.getMultiAdapter((user, self.request),
                                                IDisplayNameGenerator)()

        if not friendly_named:
            friendly_named = IFriendlyNamed(user)

        if friendly_named.realname and displayname != friendly_named.realname:
            displayname = '%s (%s)' % (friendly_named.realname, displayname)
        user_dict["displayname"] = displayname
        if friendly_named.realname:
            human_name = HumanName(friendly_named.realname)
            user_dict["last_name"] = human_name.last
            user_dict["first_name"] = human_name.first
        else:
            user_dict["last_name"] = ''
            user_dict["first_name"] = ''

    def _get_title(self, entry):
        return entry.title or u'<Empty title>'

    def _get_instructors_str(self, entry):
        names = [x.Name for x in entry.Instructors or ()]
        return u', '.join(names)

    def _get_start_date(self, entry):
        result = entry.StartDate
        if result is not None:
            result = result.strftime('%b %d, %Y')
        return result

    def _make_entry_record(self, entry):
        start_date = self._get_start_date(entry)
        instructors = self._get_instructors_str(entry)
        title = self._get_title(entry)
        return CatalogEntryRecord(title,
                                  start_date,
                                  instructors,
                                  provider_unique_id=entry.ProviderUniqueID,
                                  semester=generate_semester(entry))

    def _is_entry_visible(self, entry, course=None):
        return NotImplementedError()

    def _get_entries_and_courses(self, entries=None):
        """
        Return a sorted, dedeplicated set of course objects (entry_record, course).
        """
        if entries is None:
            entries = set()
            catalog = self.course_catalog
            if catalog is not None:
                for entry in catalog.iterCatalogEntries():
                    if self._is_entry_visible(entry):
                        entries.add(entry)

        def sort_key(entry_obj):
            title = entry_obj.title
            start = entry_obj.StartDate
            return (title is not None, title, start is not None, start)
        entries = sorted(entries, key=sort_key)
        result = []
        for entry in entries:
            course = ICourseInstance(entry, None)
            if course is not None:
                entry_record = self._make_entry_record(entry)
                result.append((entry_record, course))
        return result

    def _add_course_info(self, result, entry):
        result["title"] = self._get_title(entry)
        result['start_date'] = self._get_start_date(entry)
        result['instructors'] = self._get_instructors_str(entry)
        result['provider_unique_id'] = entry.ProviderUniqueID
        result['catalog_entry_ntiid'] = entry.ntiid

    def _add_user_info(self, result, user):
        result["username"] = user.username

        fn_user = IFriendlyNamed(user)
        self._add_name_info(user, result, friendly_named=fn_user)

        email_addressable = IEmailAddressable(user, None)
        result["email"] = email_addressable.email if email_addressable else None
        result['deactivated'] = u'Yes' if IDeactivatedUser.providedBy(user) else u''

    def _add_activity_info(self, result, user, course, record):
        # Enrollment time
        enrollment_time = None
        if record.createdTime:
            time = datetime.utcfromtimestamp(record.createdTime)
            enrollment_time = self._adjust_date(time)
            result["enrollmentTime"] = enrollment_time.strftime(u"%Y-%m-%d")
        # Last accessed
        provider = component.getMultiAdapter((user, course), ILastSeenProvider)
        accessed_time = self._adjust_date(provider.lastSeenTime) if provider.lastSeenTime else enrollment_time
        result["lastAccessed"] = self._format_datetime(accessed_time) if accessed_time else None

    def _get_entry_completion_tags(self, entry):
        """
        Look for special hidden tags of the form .<key>=<value>
        """
        result = {}
        for tag in entry.tags or ():
            if tag and is_hidden_tag(tag):
                key_val = tag.split('=')
                if len(key_val) == 2:
                    result[key_val[0]] = key_val[1]
        return result

    def _add_completion_info(self, result, progress):
        if progress.Completed:
            completed_date = self._adjust_date(progress.CompletedDate)
            completed_date = completed_date.strftime("%Y-%m-%d")
            result["completion"] = completed_date
            result["completionDate"] = completed_date
            result["completionPercentage"] = u'100%'
            result["completionSuccess"] = u'Yes' if progress.CompletedItem.Success else u'No'
        elif progress.PercentageProgress is not None:
            percent = int(progress.PercentageProgress * 100)
            result["completion"] = '%s%%' % percent
            result["completionDate"] = u''
            result["completionPercentage"] = '%s%%' % percent
            result["completionSuccess"] = u''
        else:
            # PercentageProgress returns None if the MaxPossibleProgress is 0
            # or there is no defined MaxPossibleProgress
            result["completion"] = u'N/A'
            result["completionDate"] = u''
            result["completionPercentage"] = u'N/A'
            result["completionSuccess"] = u''

    def _add_supplemental_info(self, result, user):
        if self.show_supplemental_info and self.supplemental_field_utility:
            user_supp_data = self.supplemental_field_utility.get_user_fields(user)
            if user_supp_data:
                result.update(user_supp_data)

    def _predicate_with_progress(self, progress):
        return True

    def build_enrollment_info_for_course(self, course, included_users=None, _should_include_record=None):
        """
        Return course's user enrollment info for users that are visible to the requesting user.
        """
        required_item_providers = None
        entry = ICourseCatalogEntry(course, None)
        enrollments = []
        course_enrollments = ICourseEnrollments(course)
        records = course_enrollments.iter_enrollments()
        for record in records:
            enrollment = {}

            user = User.get_user(record.Principal)
            if      user is None \
                or (included_users and user not in included_users) \
                or (_should_include_record and not _should_include_record(user, entry, course)):
                continue

            # completion
            progress_factory = CompletionContextProgressFactory(user, course, required_item_providers)
            progress = progress_factory()
            if required_item_providers is None:
                required_item_providers = progress_factory.required_item_providers

            if not self._predicate_with_progress(progress):
                continue

            self._add_completion_info(enrollment, progress)

            # user info
            self._add_user_info(enrollment, user)

            # enrolled time and last Accessed
            self._add_activity_info(enrollment, user, course, record)

            # supplemental info
            self._add_supplemental_info(enrollment, user)

            enrollments.append(enrollment)
        return enrollments

    def build_enrollment_info_for_user(self, user, included_entries=None, _should_include_record=None, records=None):
        """
        Return user's course enrollment info for courses that are visible to the requesting user.
        """
        enrollments = []
        if records is None:
            entry_ntiids = tuple([x.ntiid for x in included_entries]) if included_entries else None
            records = get_enrollment_records(usernames=(user.username,),
                                             entry_ntiids=entry_ntiids,
                                             intids=self.intids)
            records = sorted(records, key=lambda x:x.createdTime)

        for record in records:
            enrollment = {}

            course = ICourseInstance(record)
            entry = ICourseCatalogEntry(course)
            if     (included_entries and entry not in included_entries) \
                or (_should_include_record and not _should_include_record(user, entry, course)):
                continue

            # completion
            required_item_providers = self._cache_required_item_providers.get(course)
            progress_factory = CompletionContextProgressFactory(user, course, required_item_providers)
            progress = progress_factory()
            if required_item_providers is None:
                self._cache_required_item_providers[course] = progress_factory.required_item_providers

            if not self._predicate_with_progress(progress):
                continue

            self._add_completion_info(enrollment, progress)

            self._add_user_info(enrollment, user)

            # course info
            self._add_course_info(enrollment, entry)

            # enrolled time and last Accessed
            self._add_activity_info(enrollment, user, course, record)

            # supplemental info
            self._add_supplemental_info(enrollment, user)

            enrollments.append(enrollment)
        return enrollments


class AbstractEnrollmentReport(AbstractReportView,
                               EnrollmentViewMixin,
                               ModeledContentUploadRequestUtilsMixin):
    """
    <More docs>

    `profileFields` - only applicable in grouping by user. This will look for
                     a corresponding query param tied to this value. For example,
                     a `profileFields` of 'alias' will look for an 'alias' query
                     param. Only users with matching values will be in the resulting
                     report.
    """

    default_completion_not_before = None

    def __init__(self, context, request):
        AbstractReportView.__init__(self, context, request)
        EnrollmentViewMixin.__init__(self)
        self._cache_always_visible_entries = dict()
        self._cache_administered_users = dict()

    def _check_access(self):
        if not self.remoteUser:
            raise hexc.HTTPForbidden()

    @Lazy
    def course_catalog(self):
        return self.context

    @Lazy
    def is_admin(self):
        return is_admin(self.remoteUser)

    @Lazy
    def is_site_admin(self):
        return is_site_admin(self.remoteUser)

    @Lazy
    def _admin_utility(self):
        return component.getUtility(ISiteAdminUtility)

    @Lazy
    def enrolled_courses_for_requesting_user(self):
        res = set()
        for x in get_enrollments(self.remoteUser) or ():
            course = ICourseInstance(x, None)
            entry = ICourseCatalogEntry(course, None)
            if entry is not None and entry not in res:
                res.add(entry)
        return res

    def _is_enrolled_by_requesting_user(self, entry):
        return bool(entry in self.enrolled_courses_for_requesting_user)

    def _include_all_records(self, entry, course=None, cache=True):
        """
        Return True if the requesting user can access to all enrollment
        records in the given course, or False otherwise.
        """
        if entry in self._cache_always_visible_entries:
            return self._cache_always_visible_entries[entry]
        result = False
        # Instructor (who is also child site admin) in section course has
        # read permission to its parent course.
        if     self.is_admin \
            or has_permission(ACT_CONTENT_EDIT, entry) \
            or is_course_instructor(entry, self.remoteUser):
            result = True
        else:
            if course is None:
                course = ICourseInstance(entry, None)
            if course is not None and checkPermission(ACT_VIEW_REPORTS.id, course):
                result = True
        if cache:
            self._cache_always_visible_entries[entry] = result
        return result

    def _should_include_record(self, user, entry, course=None):
        """
        Return True if the requesting user can access to a user's enrollment
        record, or False otherwise.
        """
        return self._include_all_records(entry, course) or self._can_administer_user(user)

    def _is_entry_visible(self, entry, course=None):
        """
        Return True if the requesting user can access to the given course, or
        False otherwise.
        """
        return self._include_all_records(entry, course) \
            or self._is_enrolled_by_requesting_user(entry)

    def _can_administer_user(self, user, cache=True):
        if user in self._cache_administered_users:
            return self._cache_administered_users[user]

        result = False
        if self.is_admin or self.remoteUser is user:
            result =  True
        elif self.is_site_admin and self._admin_utility.can_administer_user(self.remoteUser, user):
            result = True
        if cache:
            self._cache_administered_users[user] = result
        return result

    def _raise_json_error(self, error, message):
        raise_json_error(self.request,
                         error,
                         {'message': message},
                         None)

    def _to_datetime(self, timestamp):
        return datetime.utcfromtimestamp(timestamp)

    @Lazy
    def _params(self):
        if self.request.body:
            params = self.readInput()
        else:
            params = self.request.params
        params = CaseInsensitiveDict(params)

        for field in ('course_ntiids', 'entity_ids'):
            val = params.get(field, None) or None
            if val is not None and not isinstance(val, (list, tuple)):
                self._raise_json_error(hexc.HTTPUnprocessableEntity, "%s must be a list or empty." % field)

        for field in ('completionNotBefore', 'completionNotAfter'):
            val = params.get(field, None)
            if val is not None:
                try:
                    val = float(val)
                    params[field] = self._to_datetime(val)
                except ValueError:
                    self._raise_json_error(hexc.HTTPUnprocessableEntity, "Invalid %s: %s" % (field, val))

        if      'completionNotBefore' not in params \
            and self.default_completion_not_before:
            params['completionNotBefore'] = self.default_completion_not_before
        return params

    @Lazy
    def groupByCourse(self):
        return is_true(self._params.get('groupByCourse')) if 'groupByCourse' in self._params else True

    @Lazy
    def input_users(self):
        """
        entity_ids could be ids or ntiids of user, community or group.
        """
        entity_ids = self._params.get('entity_ids', None)
        if entity_ids:
            res = set()
            for entity_id in entity_ids:
                obj = Entity.get_entity(entity_id)
                if obj is None:
                    obj = find_object_with_ntiid(entity_id)
                if obj is None:
                    self._raise_json_error(hexc.HTTPUnprocessableEntity, "No entity found (id=%s)." % entity_id)

                if IUser.providedBy(obj):
                    if obj not in res:
                        res.add(obj)
                elif ICommunity.providedBy(obj):
                    for user in obj.iter_members():
                        if user not in res:
                            res.add(user)
                elif IDynamicSharingTargetFriendsList.providedBy(obj):
                    for user in obj:
                        if user not in res:
                            res.add(user)
                else:
                    self._raise_json_error(hexc.HTTPUnprocessableEntity, "Unsupported entity (id=%s)" % entity_id)
            if not res:
                self._raise_json_error(hexc.HTTPUnprocessableEntity, "No user matched with provided entity_ids.")
            return res
        return None

    @Lazy
    def input_entries(self):
        """
        course_ntiids could be either ntiid of course instance or course catalog entry.
        """
        ntiids = self._params.get('course_ntiids', None)
        if ntiids:
            res = set()
            for ntiid in ntiids:
                obj = find_object_with_ntiid(ntiid)
                entry = ICourseCatalogEntry(obj, None)
                course = ICourseInstance(entry, None)
                if course is None:
                    self._raise_json_error(hexc.HTTPUnprocessableEntity, "Can not find course (ntiid=%s)." % ntiid)

                _catalog = find_interface(course, ICourseCatalog, strict=False)
                if _catalog is not self.course_catalog or not self._is_entry_visible(entry, course=course):
                    self._raise_json_error(hexc.HTTPForbidden, "Can not access course (title=%s)." % entry.title)

                res.add(entry)
            return res
        return None

    @Lazy
    def profile_fields(self):
        result = self._params.get('profileFields')
        if isinstance(result, six.string_types):
            result = result.split(',')
        return result

    def _get_users(self):
        result = self.input_users
        if result is None:
            if self.groupByCourse:
                result = ()
            elif self.profile_fields:
                field_values = {}
                for key in self.profile_fields:
                    field_values[key] = self._params.get(key, '')
                result = get_filtered_users_by_site(field_values, filter_deactivated=False)
            else:
                result = get_users_by_site(filter_deactivated=False)
        return result

    @Lazy
    def completionNotBefore(self):
        return self._params.get('completionNotBefore')

    @Lazy
    def completionNotAfter(self):
        return self._params.get('completionNotAfter')

    def _predicate_with_progress(self, progress):
        """
        Return a boolean if this progress record falls within our boundaries.
        """
        if not self.completionNotBefore and not self.completionNotAfter:
            return True
        return  progress.Completed \
                and (self.completionNotBefore is None or progress.CompletedDate >= self.completionNotBefore) \
                and (self.completionNotAfter is None or progress.CompletedDate < self.completionNotAfter)

    @Lazy
    def _enrollment_data_grouping_by_course(self):
        result = []
        for entry_record, course in self._get_entries_and_courses(entries=self.input_entries):
            gevent.sleep()
            enrollments = self.build_enrollment_info_for_course(course,
                                                                included_users=self.input_users,
                                                                _should_include_record=self._should_include_record)
            result.append((entry_record, enrollments))
        return result

    def _enrollment_data_grouping_by_user(self, users=None):
        result = []
        users = self._get_users() if users is None else users
        for user in users:
            gevent.sleep()
            userinfo = self.build_user_info(user)
            enrollments = self.build_enrollment_info_for_user(user,
                                                              included_entries=self.input_entries,
                                                              _should_include_record=self._should_include_record)
            if not enrollments and not self._can_administer_user(user):
                # Filter out users that have no availble enrollments and can not be administered.
                continue
            result.append((userinfo, enrollments))
        return result

    def _get_enrollment_data(self):
        return self._enrollment_data_grouping_by_course if self.groupByCourse \
                                            else self._enrollment_data_grouping_by_user()

    def _do_call(self):
        raise NotImplementedError()

    def __call__(self):
        try:
            self._check_access()
            return self._do_call()
        finally:
            self.request.environ['nti.commit_veto'] = 'abort'


@view_config(route_name='objects.generic.traversal',
             renderer="../templates/enrollment_records_report.rml",
             request_method='POST',
             context=ICourseCatalog,
             name=VIEW_ENROLLMENT_RECORDS_REPORT,
             accept='application/pdf',
             request_param=not_('format'))
@view_config(route_name='objects.generic.traversal',
             renderer="../templates/enrollment_records_report.rml",
             request_method='POST',
             context=ICourseCatalog,
             name=VIEW_ENROLLMENT_RECORDS_REPORT,
             request_param='format=application/pdf')
class EnrollmentRecordsReportPdf(AbstractEnrollmentReport):
    """
    By default it would return all user enrollment info group by course.
    """
    @Lazy
    def report_title(self):
        return _(u'Course Roster Report') if self.groupByCourse else _(u'User Enrollment Report')

    def _do_call(self):
        options = self.options
        options['groupByCourse'] = self.groupByCourse

        records = self._get_enrollment_data()
        options["records"] = records
        options["TotalRecordsCount"] = len(records)
        return options


USER_INFO_SECTION = ('Name', 'User Name', 'Email', 'Deactivated')
COURSE_INFO_SECTION = ('Course Title', 'Course Provider Unique ID', 'Course Start Date','Course Instructors')
ENROLLMENT_INFO_SECTION = ('Date Enrolled', 'Last Seen', 'Completion', 'Completed Successfully')

USER_ENROLLMENT_HEADER = USER_INFO_SECTION + COURSE_INFO_SECTION + ENROLLMENT_INFO_SECTION
COURSE_ROSTER_HEADER = COURSE_INFO_SECTION + USER_INFO_SECTION + ENROLLMENT_INFO_SECTION


class EnrollmentReportCSVMixin(object):

    @Lazy
    def header_row(self):
        raise NotImplementedError()

    def _get_enrollment_data(self):
        raise NotImplementedError()

    def _get_supplemental_header(self):
        result = []
        if self.show_supplemental_info and self.supplemental_field_utility:
            display_dict = self.supplemental_field_utility.get_field_display_values()
            supp_fields = self.supplemental_field_utility.get_ordered_fields()
            for supp_field in supp_fields:
                result.append(display_dict.get(supp_field))
        return result

    def _get_supplemental_data(self, enrollment):
        data = []
        if self.show_supplemental_info and self.supplemental_field_utility:
            supp_fields = self.supplemental_field_utility.get_ordered_fields()
            for supp_field in supp_fields:
                data.append(enrollment.get(supp_field))
        return data

    def _context_info_with_obj(self, obj):
        if self.groupByCourse:
            return {'title': obj.title,
                    'provider_unique_id': obj.provider_unique_id,
                    'start_date': obj.start_date,
                    'instructors': obj.instructors}
        else:
            return {'displayname': obj.display,
                    'username': obj.username,
                    'email': obj.email,
                    'deactivated': obj.deactivated}

    def _create_csv_file(self, stream, enrollment_data=None):
        """
        bytes - write the data in bytes
        """
        writer = csv.writer(stream, encoding='utf-8')
        # Header
        header_row = list(self.header_row)

        # Optional supplemental header
        header_row.extend(self._get_supplemental_header())

        if enrollment_data is None:
            enrollment_data = self._get_enrollment_data()

        writer.writerow(header_row)

        for obj, enrollments in enrollment_data:
            for enrollment in enrollments:
                data_row = []
                enrollment.update(self._context_info_with_obj(obj))
                for field in self.header_row:
                    # Some users for this class may have placeholder columns
                    # that we do not have info for.
                    # If we have a field in our field_map, we *must* have a value
                    # in our user data dict or it's a code error.
                    if field in self.header_field_map:
                        data_row.append(enrollment[self.header_field_map[field]])
                    else:
                        data_row.append('')

                # Optional supplemental data.
                data_row.extend(self._get_supplemental_data(enrollment))
                writer.writerow(data_row)
        stream.flush()
        stream.seek(0)

    def _do_create_response(self, filename):
        response = self.request.response
        response.content_encoding = 'identity'
        response.content_type = 'text/csv; charset=UTF-8'
        response.content_disposition = 'attachment; filename="%s"' % filename
        stream = BytesIO()
        self._create_csv_file(stream)
        response.body_file = stream
        return response


@view_config(route_name='objects.generic.traversal',
             request_method='POST',
             context=ICourseCatalog,
             name=VIEW_ENROLLMENT_RECORDS_REPORT,
             accept='text/csv',
             request_param=not_('format'))
@view_config(route_name='objects.generic.traversal',
             request_method='POST',
             context=ICourseCatalog,
             name=VIEW_ENROLLMENT_RECORDS_REPORT,
             request_param='format=text/csv')
class EnrollmentRecordsReportCSV(AbstractEnrollmentReport, EnrollmentReportCSVMixin):

    @Lazy
    def header_field_map(self):
        return {
            'Course Name': 'title', # all course roster report.
            'Course Title': 'title',
            'Course Provider Unique ID': 'provider_unique_id',
            'Course Start Date': 'start_date',
            'Course Instructors': 'instructors',

            'Name': 'displayname',
            'User Name': 'username',
            'Email': 'email',
            'Deactivated': 'deactivated',

            'Date Enrolled': 'enrollmentTime',
            'Last Seen': 'lastAccessed',
            'Completion': 'completion',
            'Completed Successfully': 'completionSuccess',
        }

    @Lazy
    def header_row(self):
        return COURSE_ROSTER_HEADER if self.groupByCourse else USER_ENROLLMENT_HEADER

    @Lazy
    def show_supplemental_info(self):
        return True

    @Lazy
    def report_title(self):
        return _(u'Course Roster Report') if self.groupByCourse else _(u'User Enrollment Report')

    def _do_call(self):
        return self._do_create_response(filename=self.filename)

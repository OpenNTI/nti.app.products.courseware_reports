#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""
from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import csv
import urllib

from nti.appserver.account_recovery_views import find_users_with_email
from nti.app.products.gradebook.interfaces import NO_SUBMIT_PART_NAME

from ..reports import _get_self_assessments_for_course
from ..reports import _do_get_containers_in_course

from zope import component

from io import BytesIO

from pyramid.view import view_config

from zope.catalog.interfaces import ICatalog
from zope.catalog.catalog import ResultSet

from zope.intid.interfaces import IIntIds

from nti.app.assessment.interfaces import ICourseAssignmentCatalog
from nti.app.assessment.interfaces import IUsersCourseAssignmentHistory

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.app.products.courseware.interfaces import ICourseCatalog
from nti.app.products.gradebook.interfaces import IGradeBook

from nti.dataserver.interfaces import IEnumerableEntityContainer

from nti.dataserver.users.entity import Entity

from nti.dataserver.metadata_index import CATALOG_NAME
from nti.dataserver.authorization import ACT_MODERATE

@view_config(route_name='objects.generic.traversal',
			 name='shared_notes',
			 renderer='rest',
			 request_method='GET',
			 permission=ACT_MODERATE)
def shared_notes(request):
	"""	Return the shared_note count by course.  The shared notes are broken down
		by public, course-only, and private."""
	stream = BytesIO()
	writer = csv.writer( stream )
	response = request.response
	response.content_encoding = str( 'identity' )
	response.content_type = str( 'text/csv; charset=UTF-8' )
	response.content_disposition = str( 'attachment; filename="shared_notes.csv"' )

	writer.writerow( ['Course', 'Public', 'Course', 'Other (Private)'] )

	def all_usernames(course):
		everyone = course.legacy_community
		everyone_usernames = {x.lower() for x in IEnumerableEntityContainer(everyone).iter_usernames()}
		return everyone_usernames

	course_catalog = component.getUtility(ICourseCatalog)
	md_catalog = component.getUtility(ICatalog,CATALOG_NAME)
	uidutil = component.getUtility(IIntIds)

	intersection = md_catalog.family.IF.intersection
	intids_of_notes = md_catalog['mimeType'].apply({'any_of': ('application/vnd.nextthought.note',)})

	for course in course_catalog:
		course = ICourseInstance(course)
		course_containers = _do_get_containers_in_course( course )
		intids_of_objects_in_course_containers = md_catalog['containerId'].apply({'any_of': course_containers})
		course_intids_of_notes = intersection( 	intids_of_notes,
												intids_of_objects_in_course_containers )
		notes = ResultSet( course_intids_of_notes, uidutil )

		scopes = course.LegacyScopes
		public = scopes['public']
		private = scopes['restricted']

		public_object = Entity.get_entity( public )
		private_object = Entity.get_entity( private )

		shared_public = 0
		shared_course = 0
		shared_other = 0

		course_users = all_usernames( course )

		notes = (x for x in notes if x.creator.username.lower() in course_users)

		for note in notes:
			if public_object in note.sharingTargets:
				shared_public += 1
			elif private_object in note.sharingTargets:
				shared_course += 1
			else:
				shared_other += 1

		writer.writerow( [course.__name__, shared_public, shared_course, shared_other] )

	stream.flush()
	stream.seek(0)
	response.body_file = stream
	return response

def _get_self_assessments_for_user( username, intids_of_submitted_qsets, self_assessment_qsids, self_assessments, md_catalog, intersection, uidutil ):
	# FIXME this logic duplicated in .views
	intids_by_student = md_catalog['creator'].apply({'any_of': (username,)})
	intids_of_submitted_qsets_by_student = intersection( 	intids_of_submitted_qsets,
															intids_by_student )
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

def _get_assignment_count(course,user,assignment_catalog):
	# FIXME this logic duplicated in .views
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

def _get_course(course_name,course_catalog):	
	for course_entry in course_catalog:
		if course_entry.__name__ == course_name:
			return ICourseInstance( course_entry )
				
@view_config(route_name='objects.generic.traversal',
			 name='whitelist_participation',
			 renderer='rest',
			 request_method='POST',
			 permission=ACT_MODERATE)
def whitelist_participation(request):
	"""	Return the participation of students found in a whitelist."""
	stream = BytesIO()
	writer = csv.writer( stream )
	response = request.response
	response.content_encoding = str( 'identity' )
	response.content_type = str( 'text/csv; charset=UTF-8' )
	response.content_disposition = str( 'attachment; filename="whitelist_participation.csv"' )

	# Inputs
	# -CSV of email addresses
	# -Course
	values = urllib.unquote( request.body )
	user_emails = set( values.split() )
	course_name = request.headers.get( 'NTcourse' )

	course_catalog = component.getUtility(ICourseCatalog)
	md_catalog = component.getUtility(ICatalog,CATALOG_NAME)
	uidutil = component.getUtility(IIntIds)
	intersection = md_catalog.family.IF.intersection

	course = _get_course(course_name,course_catalog)

	#SelfAssessments
	self_assessments = _get_self_assessments_for_course(course)
	course_self_assessment_count = len( self_assessments )
	self_assessment_qsids = {x.ntiid: x for x in self_assessments}
	intids_of_submitted_qsets = md_catalog['mimeType'].apply({'any_of': ('application/vnd.nextthought.assessment.assessedquestionset',)})

	#Assignments
	assignment_catalog = ICourseAssignmentCatalog( course )
	course_assignment_count = len( [x for x in assignment_catalog.iter_assignments()] )

	#FinalGrades
	final_grade_entry = _get_final_gradebook_entry( course )

	self_assessment_header = 'Self-Assessments Completed (%s)' % course_self_assessment_count
	assignment_header = 'Assignments Completed (%s)' % course_assignment_count
	writer.writerow( ['Email', self_assessment_header, assignment_header, 'Has Final Grade', 'Final Grade'] )

	for email in user_emails:
		users = find_users_with_email( email, dataserver=None )
		if not users:
			writer.writerow( [email + '(NOT FOUND)','N/A','N/A','No','N/A'] )
			continue
		
		if len( users ) > 1:
			# TODO What do we do here?
			# We could capture all or only capture the first or skip or combine results
			pass
		
		user = users[0]
		username = user.username.lower()
		
		#Self-Assessments
		title_to_count = _get_self_assessments_for_user(username,intids_of_submitted_qsets,self_assessment_qsids,self_assessments,md_catalog,intersection, uidutil)
		unique_self_assessment_count = sum( [1 for x in title_to_count.values() if x] )
			
		#Assignments
		unique_assignment_count = _get_assignment_count(course,user,assignment_catalog)
			
		#Final grade
		if final_grade_entry.has_key( username ):
			has_final_grade = 'Yes'
			final_grade_val = final_grade_entry[username].value
		else:
			has_final_grade = 'No'
			final_grade_val = '-'
			
		writer.writerow( [email, unique_self_assessment_count, unique_assignment_count, has_final_grade, final_grade_val] )	

	stream.flush()
	stream.seek(0)
	response.body_file = stream
	return response


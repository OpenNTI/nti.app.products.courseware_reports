#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""


.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from nti.testing import base

from nti.externalization import interfaces as ext_interfaces

import unittest

from hamcrest import *

from nti.app.products.coursewarereports.decorators import _StudentParticipationReport
from nti.app.products.coursewarereports.decorators import _ForumParticipationReport
from nti.app.products.coursewarereports.decorators import _TopicParticipationReport
from nti.app.products.coursewarereports.decorators import _CourseSummaryReport
from nti.app.products.coursewarereports.decorators import _AssignmentSummaryReport

from .. import VIEW_STUDENT_PARTICIPATION
from .. import VIEW_FORUM_PARTICIPATION
from .. import VIEW_TOPIC_PARTICIPATION
from .. import VIEW_COURSE_SUMMARY
from .. import VIEW_ASSIGNMENT_SUMMARY

LINKS = ext_interfaces.StandardExternalFields.LINKS
from nti.dataserver.links import Link

class TestDecorators(unittest.TestCase):

		def test_student_participation_decorator( self ):
			spr = _StudentParticipationReport( object(), None )
			result = {}
			spr._do_decorate_external( object(), result )

			assert( result is not None )
			assert_that( result, is_( not_none() ) )

			assert_that( result, has_entry( 'Links',
									contains( has_property( 'rel', 'report-%s' % VIEW_STUDENT_PARTICIPATION ))))

		def test_forum_participation_decorator( self ):
			spr = _ForumParticipationReport( object(), None )
			result = {}
			spr._do_decorate_external( object(), result )

			assert( result is not None )
			assert_that( result, is_( not_none() ) )

			assert_that( result, has_entry( 'Links',
									contains( has_property( 'rel', 'report-%s' % VIEW_FORUM_PARTICIPATION ))))

		def test_topic_participation_decorator( self ):
			spr = _TopicParticipationReport( object(), None )
			result = {}
			spr._do_decorate_external( object(), result )

			assert( result is not None )
			assert_that( result, is_( not_none() ) )

			assert_that( result, has_entry( 'Links',
									contains( has_property( 'rel', 'report-%s' % VIEW_TOPIC_PARTICIPATION ))))

		def test_course_summary_decorator( self ):
			spr = _CourseSummaryReport( object(), None )
			result = {}
			spr._do_decorate_external( object(), result )

			assert( result is not None )
			assert_that( result, is_( not_none() ) )

			assert_that( result, has_entry( 'Links',
									contains( has_property( 'rel', 'report-%s' % VIEW_COURSE_SUMMARY ))))

		def test_assignment_history_decorator( self ):
			spr = _AssignmentSummaryReport( object(), None )
			result = {}
			spr._do_decorate_external( object(), result )

			assert( result is not None )
			assert_that( result, is_( not_none() ) )

			assert_that( result, has_entry( 'Links',
									contains( has_property( 'rel', 'report-%s' % VIEW_ASSIGNMENT_SUMMARY ))))

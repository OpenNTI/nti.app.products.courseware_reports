

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from nti.testing import base
from nti.app.products.coursewarereports.decorators import _StudentParticipationReport
from nti.externalization import interfaces as ext_interfaces

import unittest

from hamcrest import *

from .. import VIEW_STUDENT_PARTICIPATION

LINKS = ext_interfaces.StandardExternalFields.LINKS
from nti.dataserver.links import Link

class TestDecorators(unittest.TestCase):

		def test_decorator( self ):
			spr = _StudentParticipationReport( object(), None )
			result = {}
			spr._do_decorate_external( object(), result )
		
			assert( result is not None )
			assert_that( result, is_( not_none() ) )
		
			assert_that( result, has_entry( 'Links',
									contains( has_property( 'rel', 'report-%s' % VIEW_STUDENT_PARTICIPATION ))))

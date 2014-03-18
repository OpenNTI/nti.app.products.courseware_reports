

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from nti.testing import base
from nti.app.products.coursewarereports.decorators import _StudentParticipationReport
from nti.externalization import interfaces as ext_interfaces

from hamcrest import assert_that
from hamcrest import has_property

LINKS = ext_interfaces.StandardExternalFields.LINKS
from nti.dataserver.links import Link

def test_decorator():
		spr = _StudentParticipationReport( object(), None )
		result = {}
		spr._do_decorate_external( object(), result )
		
		assert( result is not None )
		
		for lnk in result.get('Links'):
			assert( lnk is not None )
			assert( lnk.rel == 'report-StudentParticipationReport.pdf' )

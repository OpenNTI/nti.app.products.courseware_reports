from setuptools import setup, find_packages
import codecs

VERSION = '0.0.0'

entry_points = {
}

tests_require = [
	'nti.app.testing'
]

setup(
	name='nti.app.products.courseware_reports',
	version=VERSION,
	author='NextThought',
	author_email='ntiserverdev@nextthought.com',
	description="Report generation for courses",
	long_description=codecs.open('README.rst', encoding='utf-8').read(),
	license='Proprietary',
	keywords='pyramid reportlab courses reporting',
	# url = 'https://github.com/NextThought/nti.nose_traceback_info',
	classifiers=[
		'Intended Audience :: Developers',
		'Natural Language :: English',
		'Operating System :: OS Independent',
		'Programming Language :: Python :: 2',
		'Programming Language :: Python :: 2.7',
		'Programming Language :: Python :: 3',
		'Programming Language :: Python :: 3.3',
		'Framework :: Pyramid',
	],
	packages=find_packages('src'),
	package_dir={'': 'src'},
	namespace_packages=['nti', 'nti.app', 'nti.app.products'],
	install_requires=[
		'setuptools',
		'nti.app.products.courseware',
		'nti.app.products.gradebook',
		'nti.app.assessment'
		# undeclared dep on nti.dataserver
	],
	extras_require={
		'test': tests_require,
	},
	entry_points=entry_points
)

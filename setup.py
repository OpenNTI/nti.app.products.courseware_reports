from setuptools import setup, find_packages
import codecs

VERSION = '0.0.0'

entry_points = {
    "z3c.autoinclude.plugin": [
        'target = nti.app.products',
    ],
}


TESTS_REQUIRE = [
    'nti.app.products.courseware[test]',
    'nti.app.testing',
    'nti.testing',
    'zope.testrunner',
]

setup(
    name='nti.app.products.courseware_reports',
    version=VERSION,
    author='NextThought',
    author_email='josh.zuech@nextthought.com',
    description="Report generation for courses",
    long_description=codecs.open('README.rst', encoding='utf-8').read(),
    license='Proprietary',
    keywords='pyramid reportlab courses reporting',
    classifiers=[
        'Framework :: Pyramid',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: Implementation :: CPython'
    ],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    namespace_packages=['nti', 'nti.app', 'nti.app.products'],
    install_requires=[
        'setuptools',
        'z3c.rml',
        'z3c.macro',
        'z3c.pagelet',
        'z3c.template',
        'zope.viewlet',
        'zope.security',
        'zope.contentprovider',
        'nti.app.pyramid_zope',
        'nti.app.products.gradebook',
        'nti.app.products.courseware',
        'nti.app.contenttypes.reports'
    ],
    extras_require={
        'test': TESTS_REQUIRE,
    },
    entry_points=entry_points
)

from setuptools import setup

setup(
    name='django-debug-toolbar-redis',
    version='0.0.3',
    description='Simple debug toolbar panel for Redis',
    #long_description=open('README.md').read(),
    author='Clement Nodet',
    author_email='clement.nodet@gmail.com',
    url='http://github.com/clement/django-debug-toolbar-redis',
    #license='MIT',
    py_modules=['redis_panel'],
    zip_safe=True,
    classifiers=[
            'Development Status :: 4 - Beta',
            'Environment :: Web Environment',
            'Framework :: Django',
            'Intended Audience :: Developers',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
            'Topic :: Software Development :: Libraries :: Python Modules',
        ],
)


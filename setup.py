import setuptools

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

setuptools.setup(
    name='gando',
    author='Hydra',
    author_email='navidsoleymani@ymail.com',
    description="A framework based on Django that has tried to gather together the tools "
                "needed in the process of creating a large project.",
    keywords='django',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/navidsoleymani/gando.git',
    project_urls={
        'Documentation': 'https://github.com/navidsoleymani/gando.git',
        'Bug Reports':
            'https://github.com/navidsoleymani/gando.git/issues',
        'Source Code': 'https://github.com/navidsoleymani/gando.git',
    },
    package_dir={'': 'src'},
    packages=setuptools.find_packages(where='src'),
    classifiers=[
        'Framework :: Django :: 4.2',
        'Framework :: Django :: 5.0',
        'Framework :: Django :: 5.1',
        'Development Status :: 5 - Production/Stable',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        # The codebase uses PEP 604 (``X | Y``) unions at runtime, which
        # require Python 3.10+, so only 3.10+ interpreters are advertised.
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3 :: Only',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    # PEP 604 unions (e.g. ``str | None``) are evaluated at runtime in several
    # modules (management commands, schemas), so 3.8/3.9 cannot even import the
    # package. 3.10 is the true minimum.
    python_requires='>=3.10',
    install_requires=[
        # Conservative *lower* bounds only. No upper caps: gando is used with
        # modern Django (6.x) / DRF stacks and must not artificially exclude
        # them. pydantic>=2 is a hard requirement -- the code calls the v2-only
        # ``BaseModel.model_dump()`` API, which does not exist in pydantic 1.x.
        'Django>=4.2',
        'pydantic>=2.0',
        'djangorestframework>=3.14',
        'markdown>=3.4',
        'django-filter>=23.0',
        'django-simple-history>=3.3',
        'Pillow>=9.0',
        'httpx>=0.24',
    ],
)

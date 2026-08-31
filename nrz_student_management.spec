# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

project_dir = os.getcwd()

a = Analysis(
    ['launcher.py'],
    pathex=[project_dir],
    binaries=[],
    datas=[
        (os.path.join(project_dir, 'config'), 'config'),
        (os.path.join(project_dir, 'school'), 'school'),
        (os.path.join(project_dir, 'templates'), 'templates'),
        (os.path.join(project_dir, 'static'), 'static'),
    ],
    hiddenimports=[
        'django',
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'school',
        'school.models',
        'school.views',
        'school.forms',
        'school.urls',
        'school.middleware',
        'school.context_processors',
        'school.templatetags.school_tags',
        'school.utils.time_utils',
        'school.utils.audit',
        'school.reports',
        'school.management.commands.seed_students',
        'school.management.commands.progress_students_by_date',
        'school.management.commands.backup_auto',
        'school.management.commands.generate_semesters',
		'school.management.commands.seed_academic_years',
		'school.management.commands.setup_roles',
        'config.settings',
        'config.paths',
        'config.urls',
        'whitenoise',
        'whitenoise.middleware',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'django.contrib.admin.widgets',
        'django.contrib.gis',
        'django.contrib.sitemaps',
        'django.contrib.flatpages',
        'django.contrib.redirects',
        'django.contrib.syndication',
        'django.contrib.humanize',
        'test',
        'unittest',
        'doctest',
        'pdb',
        'pydoc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NRZ Student Management',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='static/favicon.ico' if os.path.exists('static/favicon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NRZ Student Management',
)